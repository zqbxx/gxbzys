import os
import threading
import time
from functools import partial
from pathlib import Path
from typing import List, Callable, Dict, TypeVar
from urllib.parse import urlparse

import PySide6
import qtawesome as qta
from PySide6.QtCore import QObject, QMutex, QEvent, Qt, QMimeData, QPoint, QSize, Signal
from PySide6.QtGui import QCursor, QIcon, QDrag, QPixmap, QDragMoveEvent, QDropEvent, QAction
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu, QFileDialog, QLabel, QWidget, QHBoxLayout

from gxbzys.dialogs import KeyMgrDialog
from gxbzys.plugin import Plugins
from gxbzys.smpv import MpvEventType, MpvCryptoEvent, CryptoType, SMPV, VideoAspects, VideoAspect, VideoRotate, \
    Tracks, PlayList, PlayListFile
from keymanager.utils import ICON_COLOR


MenuActionType = TypeVar("MenuActionType", bound="MenuAction")


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
        self.playlist = PlayList(self.player)

        self.current_playlist_file = None

        self.menu_actions: Dict[str, MenuAction] = self._build_menu_actions()
        self._install_key_bindings()

        self.check_thread = None
        self.cancel_top_thread = None

        self.player.ontop = True

        #module = __import__('dlnarender')
        #plugin_class = getattr(module, 'DLNARenderPlugin')
        self.plugins = Plugins('plugin.json', self.player)
        self.plugins.load_all()
        self.plugins.start_all()
        #self.dlna_render = YRRenderer(self.player)
        #def start_dlna_render():
        #    cli(self.dlna_render)
        #threading.Thread(target=start_dlna_render).start()

    def start(self):
        def cancel_top():
            time.sleep(1)
            self.player.ontop = False
        self.cancel_top_thread = threading.Thread(target=cancel_top)
        self.check_thread = threading.Thread(target=self._run)
        self.check_thread.start()
        self.cancel_top_thread.start()

    def event(self, event: QEvent) -> bool:

        if event.type() == MpvEventType.MpvContextMenuEventType.value:
            self._show_menu()
            return True

        elif event.type() == MpvEventType.MpvShutdownEventType.value:
            app = QApplication.instance()
            if app.activeWindow() is not None:
                app.activeWindow().close()
            self.plugins.destroy_all()
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

        actions: Dict[str, MenuAction] = {}

        MenuAction(
            name='open_local_file_act',
            action=QAction(qta.icon('ei.file-new',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '打开文件'),
            func=self._open_local_file,
        ).append_to(actions)

        MenuAction(
            name='add_local_file_act',
            action=QAction(qta.icon('mdi.playlist-plus',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '添加文件'),
            func=self._add_local_file_act,
        ).append_to(actions)
        MenuAction(
            name='save_playlist_act',
            action=QAction(qta.icon('fa.save',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '保存播放列表'),
            func=self._save_playlist_act,
        ).append_to(actions)
        MenuAction(
            name='open_playlist_act',
            action=QAction(qta.icon('fa.folder-open-o',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '打开播放列表'),
            func=self._open_playlist_act,
        ).append_to(actions)
        MenuAction(
            name='save_playlist_as_act',
            action=QAction(qta.icon('fa.folder-open-o',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '播放列表另存为'),
            func=partial(self._save_playlist_act, save_as=True),
        ).append_to(actions)

        def compare_playlist_create_date(a: PlayListFile, b: PlayListFile):
            a_t = os.stat(a.file_path).st_ctime
            b_t = os.stat(b.file_path).st_ctime
            return a_t - b_t

        def compare_playlist_name(a: PlayListFile, b: PlayListFile):
            result = 0
            ap = Path(a.file_path)
            bp = Path(b.file_path)
            if ap.parent.samefile(bp.parent):
                if str(ap.name) > str(bp.name):
                    result = 1
                elif str(ap.name) < str(bp.name):
                    result = -1
            else:
                if str(ap.parent.name) > str(bp.parent.name):
                    result = 1
                elif str(ap.parent.name) < str(bp.parent.name):
                    result = -1
            return result

        MenuAction(
            name='sort_playlist_by_name_act',
            action=QAction(qta.icon('fa.sort-alpha-asc',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '按名称排序'),
            func=partial(self._sort_playlist, comp_func=compare_playlist_name, reverse=False),
        ).append_to(actions)
        MenuAction(
            name='sort_playlist_by_name_desc_act',
            action=QAction(qta.icon('fa.sort-alpha-desc',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '按名称排序（倒序）'),
            func=partial(self._sort_playlist, comp_func=compare_playlist_name, reverse=True),
        ).append_to(actions)
        MenuAction(
            name='sort_playlist_by_time_act',
            action=QAction(qta.icon('mdi.sort-calendar-ascending',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '按时间排序（新的在前）'),
            func=partial(self._sort_playlist, comp_func=compare_playlist_create_date, reverse=False),
        ).append_to(actions)
        MenuAction(
            name='sort_playlist_by_time_desc_act',
            action=QAction(qta.icon('mdi.sort-calendar-descending',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '按时间排序（旧的在前）'),
            func=partial(self._sort_playlist, comp_func=compare_playlist_create_date, reverse=True),
        ).append_to(actions)

        MenuAction(
            name='open_key_mgr_act',
            action=QAction(qta.icon('fa5s.key',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '密钥管理'),
            func=self.key_mgr_dialog.active_exec,
        ).append_to(actions)

        video_rotate = VideoRotate(self.player)
        MenuAction(
            name='video_aspect_default_act',
            action=QAction('默认比例'),
            func=lambda: self.player.set_option('video-aspect-override', 'no'),
        ).append_to(actions)
        MenuAction(
            name='video_rotate_default_act',
            action=QAction('恢复默认'),
            func=video_rotate.rotate_reset,
        ).append_to(actions)
        MenuAction(
            name='video_rotate_left_act',
            action=QAction(qta.icon('fa.rotate-left',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向左90°'),
            func=video_rotate.rotate_left,
        ).append_to(actions)
        MenuAction(
            name='video_rotate_right_act',
            action=QAction(qta.icon('fa.rotate-right',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '向右90°'),
            func=video_rotate.rotate_right,
        ).append_to(actions)

        MenuAction(
            name='open_in_explorer_act',
            action=QAction(qta.icon('fa.folder-open-o',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '在文件夹中打开'),
            func=self._open_in_explorer,
        ).append_to(actions)

        MenuAction(
            name='clear_playlist_act',
            action=QAction(qta.icon('mdi.playlist-remove',
                                    color=ICON_COLOR['color'],
                                    color_active=ICON_COLOR['active']),
                           '清空播放列表'),
            func=self._playlist_clear,
        ).append_to(actions)

        predefined = self.video_aspect.predefined
        for video_aspect in predefined:
            MenuAction(
                name='video_aspect_' + video_aspect.get_display_name() + '_act',
                action=QAction(qta.icon('fa.square-o', color=ICON_COLOR['color']),
                               video_aspect.get_display_name()),
                func=video_aspect.set_video_aspect,
                data=video_aspect
            ).append_to(actions)

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

        def is_support_drag(action:QAction) -> bool:
            return action.data() is not None

        play_list_menu.action_support_drag = is_support_drag
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

        def time_pos_handler(name, value):
            if value is None:
                return
            self._playlist_changed()
        player.observe_property('time-pos', time_pos_handler)

        def pause_handler(name, value):
            if value:
                self._playlist_changed(force=True)
        player.observe_property('pause', pause_handler)

        @player.event_callback('file-loaded')
        def _(event):
            print('file loaded')
            self._playlist_changed(force=True)

        return player

    def _playlist_changed(self, force=False):
        if self.current_playlist_file is None:
            return
        if not Path(self.current_playlist_file).is_file():
            return
        self.playlist.save_to_file(self.current_playlist_file, force=force)

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
        self._clear_submenu(parent, 'select_playlist_')
        parent.setToolTipsVisible(True)
        parent.setToolTipDuration(1500)
        playlist = self.playlist.get_playlist()
        parent.addAction(self.menu_actions['add_local_file_act'].action)
        parent.addAction(self.menu_actions['open_playlist_act'].action)
        if len(playlist) > 0:
            need_reset = True
            if self.current_playlist_file is not None:
                p = Path(self.current_playlist_file)
                if p.exists() and p.is_file():
                    self.menu_actions['save_playlist_act'].action.setText('保存到 ' + p.name)
                    self.menu_actions['save_playlist_act'].action.setToolTip(self.current_playlist_file)
                    need_reset = False
            if need_reset:
                self.menu_actions['save_playlist_act'].action.setText('保存播放列表')
                self.menu_actions['save_playlist_act'].action.setToolTip('')

            parent.addAction(self.menu_actions['save_playlist_act'].action)
            parent.addAction(self.menu_actions['save_playlist_as_act'].action)
            parent.addAction(self.menu_actions['clear_playlist_act'].action)
            sort_menu = QMenu('排序')
            sort_menu.setIcon(qta.icon('mdi.sort', color=ICON_COLOR['color']))
            sort_menu.addAction(self.menu_actions['sort_playlist_by_name_act'].action)
            sort_menu.addAction(self.menu_actions['sort_playlist_by_name_desc_act'].action)
            sort_menu.addAction(self.menu_actions['sort_playlist_by_time_act'].action)
            sort_menu.addAction(self.menu_actions['sort_playlist_by_time_desc_act'].action)
            parent.addMenu(sort_menu)
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
            action.action.setToolTip(playlist_file.file_path)
            action.append_to(self.menu_actions)
            parent.addAction(action.action)

    def _move_playlist_file(self, source:QAction, target: QAction, parent:QMenu):
        if target.data() is None:
            return
        if source.data() is None:
            return
        self.player.playlist_move(source.data().index, target.data().index)
        parent.insertAction(target, source)
        self._playlist_changed(force=True)

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
            parent.addAction(
                MenuAction(
                    name='select_audio_track_' + track.get_display_name() + '_act',
                    action=QAction(qta.icon(icon_name, color=ICON_COLOR['color']),
                                   track.get_display_name()),
                    func=track.select,
                    data=track
                ).append_to(self.menu_actions).action)

    def _show_select_sub_submenu(self, parent: QMenu):
        self._clear_submenu(parent, 'select_sub_')

        parent.addAction(
            MenuAction(
                name='select_sub_load_external_sub_act',
                action=QAction('加载外挂字幕'),
                func=self._load_external_sub
            ).append_to(self.menu_actions).action)

        parent.addAction(
            MenuAction(
                name='select_sub_no_act',
                action=QAction('禁用字幕'),
                func=lambda : self.player.set_option('sid', 'no')
            ).append_to(self.menu_actions).action)

        tracks = Tracks(self.player, 'sub').get_tracks()

        if len(tracks) > 0:
            parent.addSeparator()

        for track in tracks:
            icon_name = 'fa.check' if track.selected else 'fa.square-o'
            parent.addAction(
                MenuAction(
                    name='select_sub_' + track.get_display_name() + '_act',
                    action=QAction(qta.icon(icon_name, color=ICON_COLOR['color']),
                                   track.get_display_name()),
                    func=track.select,
                    data=track
                ).append_to(self.menu_actions).action)

    def _open_local_file(self):
        file_list, ok = QFileDialog.getOpenFileNames(
            parent=self.key_mgr_dialog,
            caption="Open file",
            dir="",
            filter="视频文件 (*.mkv *.mp4 *.mov);;mp4 Video (*.mp4);;Movie files (*.mov);;All files (*.*)",
        )
        if ok:
            if len(file_list) > 0:
                self.player.stop()
                self.player.playlist_clear()
                self.current_playlist_file = None
                for f in file_list:
                    self.player.playlist_append(f)
                self.player.playlist_pos = 0

    def _add_local_file_act(self):
        file_list, ok = QFileDialog.getOpenFileNames(
            parent=self.key_mgr_dialog,
            caption="Open file",
            dir="",
            filter="视频文件 (*.mkv *.mp4 *.mov);;mp4 Video (*.mp4);;Movie files (*.mov);;All files (*.*)",
        )
        print(ok)
        if len(file_list) > 0:
            for f in file_list:
                self.player.playlist_append(f)

    def _save_playlist_act(self, save_as=False):

        if self.current_playlist_file is None or save_as:
            file_name, ok = QFileDialog.getSaveFileName(
                parent=self.key_mgr_dialog,
                caption="保存播放列表",
                dir='.',
                filter="播放列表 (*.gxpl)"
            )
            if not ok:
                return
            self.current_playlist_file = file_name

        playlist_file = Path(self.current_playlist_file)

        try:
            self.playlist.save_to_file(playlist_file)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _open_playlist_act(self):
        file_name, ok = QFileDialog.getOpenFileName(
            parent=self.key_mgr_dialog,
            caption="打开播放列表",
            dir='.',
            filter="播放列表 (*.gxpl)")
        if ok:
            try:
                if len(self.player.playlist) > 0:
                    self.player.stop()
                    self.player.playlist_clear()
                playlist_files: List[PlayListFile] = self.playlist.load_from_file(file_name)
                self.playlist.add_to_mpv(playlist_files)
                playlist_files_in_mpv = self.playlist.get_playlist()
                self.current_playlist_file = file_name
                found = False
                for i, f in enumerate(playlist_files):
                    if f.current:
                        for i_in_mpv, f_in_mpv in enumerate(playlist_files_in_mpv):
                            if Path(f.file_path).samefile(Path(f_in_mpv.file_path)):
                                self.player.playlist_pos = i_in_mpv
                                try:
                                    self.player.wait_until_playing()
                                    self.player.command('seek', f.time_pos, 'absolute')
                                except Exception as e:
                                    print(str(e))
                                found = True
                                break
                        break
                if not found:
                    self.player.playlist_pos = 0

            except Exception as e:
                QMessageBox.critical(None, "打开失败", str(e))

    def _sort_playlist(self, comp_func: Callable[[PlayListFile, PlayListFile], int], reverse=False):
        p = self.playlist
        playlist: List[PlayListFile] = p.get_playlist()
        length = len(playlist)
        for index in range(length):
            for j in range(1, length - index):
                result = comp_func(playlist[j - 1], playlist[j])
                if reverse:
                    result = -result
                if result > 0:
                    self.player.playlist_move(j, j - 1)
                    playlist[j - 1], playlist[j] = playlist[j], playlist[j - 1]
        self._playlist_changed(force=True)
        return playlist

    def _playlist_clear(self):
        self.player.playlist_clear()
        self.current_playlist_file = None

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
                 data=None,):
        self.name = name
        self.action = action
        self.func = func
        self.data = data

    def append_to(self, actions: Dict[str, MenuActionType]) -> MenuActionType:
        actions[self.name] = self
        return self


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

    def mousePressEvent(self, event: PySide6.QtGui.QMouseEvent) -> None:
        super().mousePressEvent(event)
        self.source_action = self.activeAction()
        if self.source_action is not None and self.action_support_drag(self.source_action):
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

    def mouseReleaseEvent(self, event: PySide6.QtGui.QMouseEvent) -> None:
        # 触发keypress以后如果没有触发dragMoveEvent则mouseReleaseEvent不会触发
        # 全部放到dropEvent中处理

        if self.source_action is None or not self.action_support_drag(self.source_action):
            super().mouseReleaseEvent(event)

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

        if action is not None and self.action_support_drag(action):
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
    def source_action(self) -> QAction:
        if not hasattr(self, '_source_action'):
            return None
        return self._source_action

    @source_action.setter
    def source_action(self, source_action: QAction):
        self._source_action = source_action

    @property
    def action_support_drag(self)-> Callable[[QAction], bool]:
        def default_true(action: QAction)->bool:
            return True
        if not hasattr(self, '_action_support_drag'):
            return default_true
        return self._action_support_drag

    @action_support_drag.setter
    def action_support_drag(self, action_support_drag: Callable[[QAction], bool]):
        self._action_support_drag = action_support_drag

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
