import os
import platform
import threading
import time
from enum import Enum
from typing import Dict, Callable
from urllib.parse import urlparse, parse_qs

import qtawesome as qta
from PyQt5.QtCore import QMutex, QPoint, Qt, QEvent, QObject
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QAction, QMenu, QFileDialog

from gxbzys.dialogs import KeyMgrDialog

from gxbzys.mpv import MPV, StreamOpenFn, StreamReadFn, StreamCloseFn, StreamSeekFn, StreamSizeFn, register_protocol
from gxbzys.video import VideoStream
from keymanager.key import KEY_CACHE


class SMPV(MPV):

    def __init__(self, *extra_mpv_flags, log_handler=None, start_event_thread=True, loglevel=None, **extra_mpv_opts):
        super().__init__(*extra_mpv_flags, log_handler=log_handler, start_event_thread=start_event_thread,
                         loglevel=loglevel, **extra_mpv_opts)

        self.register_crypto_protocol()
        self.opened_streams = {}

    def _crypto_stream_open(self, uri: str):
        result = urlparse(uri)
        file_path: str = result.path
        if platform.system() == 'Windows':
            if file_path.startswith('/'):
                file_path = file_path[1:]

        key_index = 0
        query = parse_qs(result.query)
        if 'key' in query:
            values = query.get('key')
            if len(values) > 0:
                key_index = int(values[0])

        key = KEY_CACHE.get_cur_key()

        stream = VideoStream(file_path, key.key)
        return stream

    def register_crypto_protocol(self):
        @StreamOpenFn
        def _open(_userdata, uri, cb_info):
            stream = self._crypto_stream_open(uri.decode('utf-8'))
            stream.open()

            def read(_userdata, buf, bufsize):
                data = stream.read(bufsize)
                for i in range(len(data)):
                    buf[i] = data[i]
                return len(data)

            def close(_userdata):
                stream.close()

            def seek(_userdata, offset):
                return stream.seek(offset)

            def size(_userdata):
                return stream.head.raw_file_size

            cb_info.contents.cookie = None
            _read = cb_info.contents.read = StreamReadFn(read)
            _close = cb_info.contents.close = StreamCloseFn(close)
            _seek = cb_info.contents.seek = StreamSeekFn(seek)
            _size = cb_info.contents.size = StreamSizeFn(size)

            stream._mpv_callbacks_ = [_read, _close, _seek, _size]

            self.opened_streams[uri.decode('utf-8')] = stream

            return 0

        self._stream_protocol_cbs['crypto'] = [_open]
        register_protocol(self.handle, 'crypto', _open)


class MpvEventType(Enum):
    MpvContextMenuEventType = QEvent.Type(QEvent.registerEventType())
    MpvShutdownEventType = QEvent.Type(QEvent.registerEventType())
    MpvOpenDialogEventType = QEvent.Type(QEvent.registerEventType())


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

        self.menu_actions: Dict[str, MenuAction] = self._build_menu_actions()
        self.pop_menu = self._create_menus()
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

        return super().event(event)

    def _run(self):
        while not self._exit_flag:
            if self.player.core_shutdown:
                event = QEvent(MpvEventType.MpvShutdownEventType.value)
                QApplication.instance().postEvent(self, event)
                return
            time.sleep(0.1)

    def _init_pyqt(self):
        self.pop_menu.popup(QPoint(20000, 10000))
        self.pop_menu.close()

    def _build_menu_actions(self):
        open_local_file_act: MenuAction = MenuAction(
            name='open_local_file_act',
            action=QAction(qta.icon('ei.file-new', color='#8a949a', color_active='black'), '打开文件'),
            func=self._open_local_file)
        open_key_mgr_act: MenuAction = MenuAction(
            name='open_key_mgr_act',
            action=QAction(qta.icon('fa5s.key', color='#8a949a', color_active='black'), '密钥管理'),
            func=self.key_mgr_dialog.active_exec)
        return {
            open_local_file_act.name: open_local_file_act,
            open_key_mgr_act.name: open_key_mgr_act
        }

    def _create_menus(self):
        pop_menu = QMenu()
        pop_menu.setContextMenuPolicy(Qt.CustomContextMenu)
        pop_menu.addAction(self.menu_actions['open_local_file_act'].action)
        pop_menu.addAction(self.menu_actions['open_key_mgr_act'].action)
        return pop_menu

    def _create_player(self):
        print(os.path.abspath('./config'))
        player = SMPV(ytdl=True,
                      player_operation_mode='pseudo-gui',
                      autofit='70%',
                      # script_opts='osc-layout=bottombar,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3',
                      input_default_bindings=True,
                      input_vo_keyboard=True,
                      log_handler=print,
                      loglevel='info',
                      config_dir='./config',
                      input_conf="./config/input.conf",
                      border=False,
                      osd_bar=False,
                      osc=False)
        player.command('load-script', os.path.abspath('./config/scripts/crypto.lua'))
        player.command('load-script', os.path.abspath('./config/scripts/uosc.lua'))
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
        selected_action = self.pop_menu.exec(QCursor.pos())
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
            for f in file_list:
                self.player.playlist_append(f)
            self.player.playlist_pos = 0

    def _open_key_mgr(self):
        self.key_mgr_dialog.active_exec()

class MenuAction:

    def __init__(self,
                 name: str,
                 action: QAction,
                 func: Callable):
        self.name = name
        self.action = action
        self.func = func
