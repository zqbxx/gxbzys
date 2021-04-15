import threading
import time
from typing import List, Callable, Dict

import qtawesome as qta
from PySide2.QtCore import QObject, QMutex, QEvent, QPoint, Qt
from PySide2.QtGui import QCursor
from PySide2.QtWidgets import QApplication, QMessageBox, QAction, QMenu, QFileDialog

from gxbzys.dialogs import KeyMgrDialog
from gxbzys.smpv import MpvEventType, MpvCryptoEvent, CryptoType, SMPV, VideoAspects, VideoAspect, VideoRotate
from keymanager.utils import ICON_COLOR


class SMPVPlayer(QObject):

    def __init__(self, parent:QObject = None):

        super().__init__(parent)

        self.app = QApplication.instance()
        self.key_mgr_dialog = KeyMgrDialog(model=False)

        self._exit_flag = False

        self.thread_dict = {}
        self.thread_cnt = 0
        self.thread_lock = QMutex()

        self.player = self._create_player()
        self.video_aspect = self._create_aspect()
        self.video_rotate = VideoRotate(self.player)

        self.menu_actions: Dict[str, MenuAction] = self._build_menu_actions()
        #self.pop_menu = self._create_menus()
        self._init_pyqt()
        self._install_key_bindings()

        self.check_thread = None

    def start(self):
        self.check_thread = threading.Thread(target=self._run)
        self.check_thread.start()

    def event(self, event: QEvent) -> bool:

        if event.type() == MpvEventType.MpvContextMenuEventType.value:
            self._show_menu()
            return True

        elif event.type() == MpvEventType.MpvShutdownEventType.value:
            app = QApplication.instance()
            if app.activeWindow() is not None:
                app.activeWindow().close()
            self.player.terminate()
            self.key_mgr_dialog.close()
            self.app.closeAllWindows()
            self.app.quit()
            self.app.exit(0)
            return True

        elif event.type() == MpvEventType.MpvCryptoEventType.value:
            e: MpvCryptoEvent = event
            if e.crypto_type == CryptoType.nokey:
                msg = '没有加载默认的密钥'
            elif e.crypto_type == CryptoType.timeout:
                msg = '默认密钥已经超时，需重新加载'
            else:
                msg = '未知错误:' + str(e.crypto_type)
            QMessageBox.critical(None, '错误', msg)
            return True

        return super().event(event)

    def _run(self):
        while not self._exit_flag:
            if self.player.core_shutdown:
                event = QEvent(MpvEventType.MpvShutdownEventType.value)
                QApplication.instance().postEvent(self, event)
                return
            time.sleep(0.1)

    def _init_pyqt(self):
        #self.pop_menu.popup(QPoint(20000, 10000))
        #self.pop_menu.close()
        pass

    def _create_aspect(self):
        video_aspect = VideoAspects(self.player)
        video_aspect.add_predefined_aspect(4, 3)
        video_aspect.add_predefined_aspect(16, 9)
        video_aspect.add_predefined_aspect(2.35, 1)
        return video_aspect

    def _build_menu_actions(self):
        open_local_file_act: MenuAction = MenuAction(
            name='open_local_file_act',
            action=QAction(qta.icon('ei.file-new',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '打开文件'),
            func=self._open_local_file)

        add_local_file_act: MenuAction = MenuAction(
            name='add_local_file_act',
            action=QAction(qta.icon('mdi.playlist-plus',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '添加文件'),
            func=self._add_local_file_act)

        open_key_mgr_act: MenuAction = MenuAction(
            name='open_key_mgr_act',
            action=QAction(qta.icon('fa5s.key',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '密钥管理'),
            func=self.key_mgr_dialog.active_exec)

        video_aspect_default_act: MenuAction = MenuAction(
            name='video_aspect_default_act',
            action=QAction('默认比例'),
            func=lambda: self.player.set_option('video-aspect-override', 'no')
        )

        video_rotate_default_act: MenuAction = MenuAction(
            name='video_rotate_default_act',
            action=QAction('恢复默认'),
            func=self.video_rotate.rotate_reset
        )

        video_rotate_left_act: MenuAction = MenuAction(
            name='video_rotate_left_act',
            action=QAction(qta.icon('fa.rotate-left',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向左90°'),
            func=self.video_rotate.rotate_left
        )

        video_rotate_right_act: MenuAction = MenuAction(
            name='video_rotate_right_act',
            action=QAction(qta.icon('fa.rotate-right',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向右90°'),
            func=self.video_rotate.rotate_right
        )

        actions = {
            open_local_file_act.name: open_local_file_act,
            add_local_file_act.name: add_local_file_act,
            open_key_mgr_act.name: open_key_mgr_act,
            video_aspect_default_act.name: video_aspect_default_act,
            video_rotate_default_act.name: video_rotate_default_act,
            video_rotate_left_act.name: video_rotate_left_act,
            video_rotate_right_act.name: video_rotate_right_act
        }

        predefined = self.video_aspect.predefined
        for video_aspect in predefined:
            action: MenuAction = MenuAction(
                name='video_aspect_' + video_aspect.get_display_name() + '_act',
                action=QAction(qta.icon('fa.square-o', color=ICON_COLOR['color']),
                               video_aspect.get_display_name()),
                func=video_aspect.set_video_aspect,
                data=video_aspect
            )
            actions[action.name] = action

        return actions

    def _create_menus(self):

        params = self.player.video_params

        pop_menu = QMenu()
        pop_menu.setContextMenuPolicy(Qt.CustomContextMenu)
        pop_menu.addAction(self.menu_actions['open_local_file_act'].action)
        pop_menu.addAction(self.menu_actions['add_local_file_act'].action)

        video_aspect_menu = QMenu('画面比例')
        video_rotate_menu = QMenu('画面旋转')
        video_aspect_menu.setIcon(qta.icon('mdi.aspect-ratio',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        video_rotate_menu.setIcon(qta.icon('mdi.crop-rotate',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))

        pop_menu.addMenu(video_aspect_menu)
        pop_menu.addMenu(video_rotate_menu)

        video_rotate_menu.addAction(self.menu_actions['video_rotate_default_act'].action)
        video_rotate_menu.addAction(self.menu_actions['video_rotate_left_act'].action)
        video_rotate_menu.addAction(self.menu_actions['video_rotate_right_act'].action)

        is_video_ready = self.video_aspect.is_video_ready()

        if is_video_ready:
            aspect_index = self.video_aspect.get_current_aspect_index()
            if aspect_index == -1:
                current_aspect = None
            else:
                current_aspect = self.video_aspect.predefined[aspect_index]

        for name, action in self.menu_actions.items():
            if name.startswith('video_aspect_'):
                if is_video_ready:
                    if current_aspect is not None and action.data is not None:
                        aspect: VideoAspect = action.data
                        if aspect.get_option_value() == current_aspect.get_option_value():
                            action.action.setIcon(qta.icon('fa.check', color=ICON_COLOR['color']))
                        else:
                            action.action.setIcon(qta.icon('fa.square-o', color=ICON_COLOR['color']))
                video_aspect_menu.addAction(action.action)

        pop_menu.addAction(self.menu_actions['open_key_mgr_act'].action)
        return pop_menu

    def _create_player(self):

        player = SMPV(
            event_object=self,
            ytdl=True,
            player_operation_mode='pseudo-gui',
            autofit='70%',
            #script_opts='osc-layout=bottombar,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3',
            input_default_bindings=True,
            input_vo_keyboard=True,
            log_handler=print,
            loglevel='info',
            config_dir='./config',
            config='yes',
            border=False,
            osd_bar=False,
            osc=False)

        @player.message_handler('show-menu')
        def my_handler(*args):
            event = QEvent(MpvEventType.MpvContextMenuEventType.value)
            QApplication.instance().postEvent(self, event)

        return player

    def _install_key_bindings(self):
        @self.player.on_key_press('ctrl+q')
        def ctrl_q():
            event = QEvent(MpvEventType.MpvShutdownEventType.value)
            QApplication.instance().postEvent(self, event)

        @self.player.on_key_press('mbtn_right')
        def mbtn_right():
            event = QEvent(MpvEventType.MpvContextMenuEventType.value)
            QApplication.instance().postEvent(self, event)

    def _show_menu(self):
        pop_menu = self._create_menus()
        selected_action = pop_menu.exec_(QCursor.pos())
        for name, menu_action in self.menu_actions.items():
            if menu_action.action == selected_action:
                menu_action.func()

    def _open_local_file(self):
        file_list, ok = QFileDialog.getOpenFileNames(
            parent=self.key_mgr_dialog,
            caption="Open file",
            directory="",
            filter="mkv Video (*.mkv);;mp4 Video (*.mp4);;Movie files (*.mov);;All files (*.*)",
        )
        print(ok)
        if len(file_list) > 0:
            self.player.playlist_clear()
            for f in file_list:
                self.player.playlist_append(f)
            self.player.playlist_pos = 0

    def _add_local_file_act(self):
        file_list, ok = QFileDialog.getOpenFileNames(
            parent=self.key_mgr_dialog,
            caption="Open file",
            directory="",
            filter="mkv Video (*.mkv);;mp4 Video (*.mp4);;Movie files (*.mov);;All files (*.*)",
        )
        print(ok)
        if len(file_list) > 0:
            for f in file_list:
                self.player.playlist_append(f)

    def _open_key_mgr(self):
        self.key_mgr_dialog.active_exec()


class MenuAction:

    def __init__(self,
                 name: str,
                 action: QAction,
                 func: Callable,
                 data=None):
        self.name = name
        self.action = action
        self.func = func
        self.data = data
