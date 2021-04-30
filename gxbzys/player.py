import os
import threading
import time
from functools import partial
from pathlib import Path
from typing import List, Callable, Dict
from urllib.parse import urlparse

import PySide2
import qtawesome as qta
from PySide2.QtCore import QObject, QMutex, QEvent, Qt, QMimeData, QPoint, QSize, Signal
from PySide2.QtGui import QCursor, QIcon, QDrag, QPixmap, QDragMoveEvent, QDropEvent
from PySide2.QtWidgets import QApplication, QMessageBox, QAction, QMenu, QFileDialog, QLabel, QWidget, QHBoxLayout

from gxbzys.dialogs import KeyMgrDialog
from gxbzys.smpv import MpvEventType, MpvCryptoEvent, CryptoType, SMPV, VideoAspects, VideoAspect, VideoRotate, \
    Tracks
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

        self.menu_actions: Dict[str, MenuAction] = self._build_menu_actions()
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

    def _create_aspect(self):
        video_aspect = VideoAspects(self.player)
        video_aspect.add_predefined_aspect(9, 16)
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
        video_rotate = VideoRotate(self.player)
        video_rotate_default_act: MenuAction = MenuAction(
            name='video_rotate_default_act',
            action=QAction('恢复默认'),
            func=video_rotate.rotate_reset
        )

        video_rotate_left_act: MenuAction = MenuAction(
            name='video_rotate_left_act',
            action=QAction(qta.icon('fa.rotate-left',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向左90°'),
            func=video_rotate.rotate_left
        )

        video_rotate_right_act: MenuAction = MenuAction(
            name='video_rotate_right_act',
            action=QAction(qta.icon('fa.rotate-right',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向右90°'),
            func=video_rotate.rotate_right
        )

        open_in_explorer_act: MenuAction = MenuAction(
            name='open_in_explorer_act',
            action=QAction(qta.icon('fa.folder-open-o',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '在文件夹中打开'),
            func=self._open_in_explorer
        )

        clear_playlist_act: MenuAction = MenuAction(
            name='clear_playlist_act',
            action=QAction(qta.icon('mdi.playlist-remove',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '清空播放列表'),
            func=lambda: self.player.playlist_clear()
        )

        actions = {
            open_local_file_act.name: open_local_file_act,
            add_local_file_act.name: add_local_file_act,
            open_key_mgr_act.name: open_key_mgr_act,
            video_aspect_default_act.name: video_aspect_default_act,
            video_rotate_default_act.name: video_rotate_default_act,
            video_rotate_left_act.name: video_rotate_left_act,
            video_rotate_right_act.name: video_rotate_right_act,
            open_in_explorer_act.name: open_in_explorer_act,
            clear_playlist_act.name: clear_playlist_act
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

        pop_menu = QMenu()
        pop_menu.setContextMenuPolicy(Qt.CustomContextMenu)
        pop_menu.addAction(self.menu_actions['open_local_file_act'].action)

        # 播放列表
        play_list_menu = QDraggableMenu('播放列表')
        play_list_menu.root_menu = pop_menu
        play_list_menu.setAcceptDrops(True)
        play_list_menu.setIcon(qta.icon('mdi.playlist-music-outline',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        play_list_menu.icon_on_drag_hover = qta.icon('mdi.arrow-top-right-bold-outline',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active'])
        play_list_menu.aboutToShow.connect(partial(self._show_playlist_submenu, parent=play_list_menu))
        play_list_menu.drop_done.connect(self._move_playlist_file)
        pop_menu.addMenu(play_list_menu)

        # 画面比例
        video_aspect_menu = QMenu('画面比例')
        video_aspect_menu.setIcon(qta.icon('mdi.aspect-ratio',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        video_aspect_menu.aboutToShow.connect(partial(self._show_aspect_submenu, parent=video_aspect_menu))
        pop_menu.addMenu(video_aspect_menu)

        # 画面旋转
        video_rotate_menu = QMenu('画面旋转')
        video_rotate_menu.setIcon(qta.icon('mdi.crop-rotate',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        pop_menu.addMenu(video_rotate_menu)
        video_rotate_menu.addAction(self.menu_actions['video_rotate_default_act'].action)
        video_rotate_menu.addSeparator()
        video_rotate_menu.addAction(self.menu_actions['video_rotate_left_act'].action)
        video_rotate_menu.addAction(self.menu_actions['video_rotate_right_act'].action)

        # 字幕
        sub_select_menu = QMenu('字幕')
        sub_select_menu.setIcon(qta.icon('mdi.timeline-text-outline',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        sub_select_menu.aboutToShow.connect(partial(self._show_select_sub_submenu, parent=sub_select_menu))
        pop_menu.addMenu(sub_select_menu)

        # 音轨
        audio_select_menu = QMenu('音轨')
        audio_select_menu.setIcon(qta.icon('ei.music',
                                           color=ICON_COLOR['color'],
                                           color_active=ICON_COLOR['active']))
        audio_select_menu.aboutToShow.connect(partial(self._show_select_audio_track_submenu, parent=audio_select_menu))
        pop_menu.addMenu(audio_select_menu)

        pop_menu.addAction(self.menu_actions['open_key_mgr_act'].action)
        pop_menu.addAction(self.menu_actions['open_in_explorer_act'].action)
        return pop_menu

    def _create_player(self):

        player = SMPV(
            event_object=self,
            ytdl=False,
            player_operation_mode='pseudo-gui',
            autofit='70%',
            input_default_bindings=True,
            input_vo_keyboard=True,
            log_handler=print,
            loglevel='info',
            config_dir='./config',
            config='yes',
            border=False,
            osd_bar=False,
            #msg_level='cplayer=debug',
            terminal=True,
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
        if selected_action is None and hasattr(pop_menu, '_selected_action'):
            selected_action = pop_menu._selected_action
        if selected_action is None:
            return
        for name, menu_action in self.menu_actions.items():
            if menu_action.action == selected_action:
                menu_action.func()

    def _clear_submenu(self, parent: QMenu, key: str=None):
        parent.clear()
        if key is None:
            return
        deleted:List[str] = []
        for action_name in self.menu_actions.keys():
            if action_name.startswith(key):
                deleted.append(action_name)
        for action_name in deleted:
            del self.menu_actions[action_name]

    def _show_playlist_submenu(self, parent: QMenu):
        from gxbzys.smpv import PlayList
        self._clear_submenu(parent, 'select_playlist_')
        parent.setToolTipsVisible(True)
        parent.setToolTipDuration(1500)
        playlist = PlayList(self.player).get_playlist()
        parent.addAction(self.menu_actions['add_local_file_act'].action)
        if len(playlist) > 0:
            parent.addAction(self.menu_actions['clear_playlist_act'].action)
            parent.addSeparator()

        for playlist_file in playlist:
            action_icon = QIcon()

            if playlist_file.playing:
                action_icon = qta.icon('fa.play-circle-o', color=ICON_COLOR['color'])
            elif playlist_file.current:
                action_icon = qta.icon('fa.pause-circle-o', color=ICON_COLOR['color'])

            action: MenuAction = MenuAction(
                name='select_playlist_' + playlist_file.get_display_name() + '_act',
                action=QAction(action_icon, playlist_file.get_display_name()),
                func=playlist_file.select,
                data=playlist_file
            )
            action.action.setData(playlist_file)
            self.menu_actions[action.name] = action
            action.action.setToolTip(playlist_file.file_path)
            parent.addAction(action.action)

    def _move_playlist_file(self, source:QAction, target: QAction, parent:QMenu):
        if target.data() is None:
            return
        self.player.playlist_move(source.data().index, target.data().index)
        parent.insertAction(target, source)

    def _show_aspect_submenu(self, parent: QMenu):
        self._clear_submenu(parent)
        is_video_ready = self.video_aspect.is_video_ready()

        if is_video_ready:
            aspect_index = self.video_aspect.get_current_aspect_index()
            if aspect_index == -1:
                current_aspect = None
            else:
                current_aspect = self.video_aspect.predefined[aspect_index]

        for name, action in self.menu_actions.items():

            if name == 'video_aspect_default_act':
                parent.addAction(action.action)
                parent.addSeparator()
                continue

            if name.startswith('video_aspect_'):
                if is_video_ready:
                    if current_aspect is None:
                        action.action.setIcon(qta.icon('fa.square-o', color=ICON_COLOR['color']))
                    elif action.data is not None:
                        aspect: VideoAspect = action.data
                        if aspect.get_option_value() == current_aspect.get_option_value():
                            action.action.setIcon(qta.icon('fa.check', color=ICON_COLOR['color']))
                        else:
                            action.action.setIcon(qta.icon('fa.square-o', color=ICON_COLOR['color']))
                parent.addAction(action.action)

    def _show_select_audio_track_submenu(self, parent: QMenu):
        self._clear_submenu(parent, 'select_audio_track_')
        tracks = Tracks(self.player, 'audio').get_tracks()
        for track in tracks:
            icon_name = 'fa.check' if track.selected  else 'fa.square-o'
            action: MenuAction = MenuAction(
                name='select_audio_track_' + track.get_display_name() + '_act',
                action=QAction(qta.icon(icon_name, color=ICON_COLOR['color']),
                               track.get_display_name()),
                func=track.select,
                data=track
            )
            self.menu_actions[action.name] = action
            parent.addAction(action.action)

    def _show_select_sub_submenu(self, parent: QMenu):
        self._clear_submenu(parent, 'select_sub_')

        action: MenuAction = MenuAction(
            name='select_sub_load_external_sub_act',
            action=QAction('加载外挂字幕'),
            func=self._load_external_sub
        )
        self.menu_actions[action.name] = action
        parent.addAction(action.action)

        action: MenuAction = MenuAction(
            name='select_sub_no_act',
            action=QAction('禁用字幕'),
            func=lambda : self.player.set_option('sid', 'no')
        )
        self.menu_actions[action.name] = action
        parent.addAction(action.action)

        tracks = Tracks(self.player, 'sub').get_tracks()

        if len(tracks) > 0:
            parent.addSeparator()

        for track in tracks:
            icon_name = 'fa.check' if track.selected else 'fa.square-o'
            action: MenuAction = MenuAction(
                name='select_sub_' + track.get_display_name() + '_act',
                action=QAction(qta.icon(icon_name, color=ICON_COLOR['color']),
                               track.get_display_name()),
                func=track.select,
                data=track
            )
            self.menu_actions[action.name] = action
            parent.addAction(action.action)

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

    def _open_in_explorer(self):

        if self.player.path is None:
            return

        url = urlparse(self.player.path)

        if not (url.netloc == ''):
            return

        file_path = Path(self.player.path)

        if not file_path.is_file():
            return

        if not file_path.parent.is_dir():
            return

        os.startfile(file_path.parent)

    def _load_external_sub(self):

        if self.player.path is None:
            return

        url = urlparse(self.player.path)

        if not (url.netloc == ''):
            return

        file_path = Path(self.player.path)

        if not file_path.is_file():
            return

        if not file_path.parent.is_dir():
            return

        sub_path, ok = QFileDialog.getOpenFileName(
            parent=None,
            caption="选择字幕",
            dir=str(file_path.parent),
            filter="srt (*.srt);;ass (*.ass)",
        )
        print(ok)
        if sub_path:
            self.player.command('sub-add', sub_path)


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


class IconLabel(QWidget):
    IconSize = QSize(16, 16)
    HorizontalSpacing = 2

    def __init__(self, icon: QIcon, text, final_stretch=True):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        label = QLabel()
        label.setPixmap(icon.pixmap(self.IconSize))
        layout.addWidget(label)
        layout.addSpacing(self.HorizontalSpacing)
        layout.addWidget(QLabel(text))
        if final_stretch:
            layout.addStretch()


class QDraggableMenu(QMenu):

    drop_done = Signal(QAction, QAction, QMenu)

    def defaultDropDone(self, source: QAction, target: QAction, parent: QMenu):
        parent.insertAction(target, source)

    def mousePressEvent(self, event: PySide2.QtGui.QMouseEvent) -> None:
        super().mousePressEvent(event)
        self.source_action = self.activeAction()
        if self.source_action is not None:
            drag = QDrag(self.source_action)
            t_menu = QMenu(self.source_action.text())
            t_menu.setIcon(self.source_action.icon())
            label = IconLabel(self.source_action.icon(), self.source_action.text())
            drag.setPixmap(QPixmap.grabWidget(label))
            drag.setHotSpot(QPoint(5, 5))
            mimedata = QMimeData()
            mimedata.setText(self.source_action.text())
            drag.setMimeData(mimedata)
            drag.exec_()

    def mouseReleaseEvent(self, event: PySide2.QtGui.QMouseEvent) -> None:
        # 触发keypress以后如果没有触发dragMoveEvent则mouseReleaseEvent不会触发
        # 全部放到dropEvent中处理
        pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('text/plain'):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if not hasattr(self, 'last_hover_action'):
            self.last_hover_action = None
            self.last_hover_action_icon = None
        action: QAction = self.actionAt(event.pos())
        print(f'self.source_action == action: {self.source_action == action}')
        if self.source_action == action:
            self.is_in_drop_status = False
            return

        if action is not None:
            self.is_in_drop_status = True
            if self.last_hover_action is not None:
                self.last_hover_action.setIcon(self.last_hover_action_icon)
            self.last_hover_action = action
            self.last_hover_action_icon = action.icon()
            if self.icon_on_drag_hover is not None:
                action.setIcon(self.icon_on_drag_hover)

    def dropEvent(self, event: QDropEvent):
        if not self.is_in_drop_status:
            action = self.actionAt(event.pos())
            self.root_menu._selected_action = action
            self.root_menu.close()
            return

        if self.last_hover_action is not None:
            self.last_hover_action.setIcon(self.last_hover_action_icon)
        action = self.actionAt(event.pos())
        if self.source_action is not None and self.source_action != action:
            self.drop_done.emit(self.source_action, action, self)

        self.is_in_drop_status = False

    @property
    def last_hover_action_icon(self) -> QIcon:
        if not hasattr(self, '_last_hover_action_icon'):
            return None
        return self._last_hover_action_icon

    @last_hover_action_icon.setter
    def last_hover_action_icon(self, last_hover_action_icon: QIcon):
        self._last_hover_action_icon = last_hover_action_icon

    @property
    def last_hover_action(self) -> QAction:
        if not hasattr(self, '_last_hover_action'):
            return None
        return self._last_hover_action

    @last_hover_action.setter
    def last_hover_action(self, last_hover_action:QAction):
        self._last_hover_action = last_hover_action

    @property
    def root_menu(self) -> QMenu:
        return self._root_menu

    @root_menu.setter
    def root_menu(self, root_menu: QMenu):
        self._root_menu = root_menu

    @property
    def icon_on_drag_hover(self) -> QIcon:
        if not hasattr(self, '_icon_on_drag_hover'):
            return None
        return self._icon_on_drag_hover

    @icon_on_drag_hover.setter
    def icon_on_drag_hover(self, icon_on_drag_hover: QIcon):
        self._icon_on_drag_hover = icon_on_drag_hover
