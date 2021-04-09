import os
import platform
import threading
import time
import typing
from enum import Enum
from typing import Dict, Callable
from urllib.parse import urlparse, parse_qs

import qtawesome as qta
from PyQt5.QtCore import QMutex, QPoint, Qt, QEvent, QObject
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QAction, QMenu, QFileDialog, QMessageBox

from gxbzys.dialogs import KeyMgrDialog

from gxbzys import mpv
from gxbzys.mpv import MPV, StreamOpenFn, StreamReadFn, StreamCloseFn, StreamSeekFn, StreamSizeFn, register_protocol
from gxbzys.video import VideoStream
from keymanager.key import KEY_CACHE
from keymanager.utils import ICON_COLOR


class EmptyStream:

    def read(self, length):
        return ''

    def seek(self, pos):
        return 0

    def tell(self):
        return 0

    def close(self):
        pass

    def open(self):
        pass


class SMPV(MPV):

    def __init__(self,
                 event_object: QObject = None,
                 *extra_mpv_flags,
                 log_handler=None,
                 start_event_thread=True,
                 loglevel=None,
                 **extra_mpv_opts):
        super().__init__(*extra_mpv_flags, log_handler=log_handler, start_event_thread=start_event_thread,
                         loglevel=loglevel, **extra_mpv_opts)

        self.register_crypto_protocol()
        self.opened_streams = {}
        self.event_object: QObject = event_object

    def load_config(self, path: str):
        mpv._mpv_load_config_file(self.handle, path.encode('utf-8'))

    def _crypto_stream_open(self, uri: str):
        result = urlparse(uri)
        file_path: str = result.path
        if platform.system() == 'Windows':
            if file_path.startswith('/'):
                file_path = file_path[1:]

        key = KEY_CACHE.get_cur_key()

        if key is None:
            if self.event_object is not None:
                event = MpvCryptoEvent(CryptoType.nokey, MpvEventType.MpvCryptoEventType.value)
                QApplication.instance().postEvent(self.event_object, event)
            self.stream_open_filename = ''
            return EmptyStream()

        if key.timeout:
            if self.event_object is not None:
                event = MpvCryptoEvent(CryptoType.timeout, MpvEventType.MpvCryptoEventType.value)
                QApplication.instance().postEvent(self.event_object, event)
            self.stream_open_filename = ''
            return EmptyStream()

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
            # TODO 流关闭时移除opened_streams的value
            self.opened_streams[uri.decode('utf-8')] = stream

            return 0

        self._stream_protocol_cbs['crypto'] = [_open]
        register_protocol(self.handle, 'crypto', _open)


class MpvEventType(Enum):
    MpvContextMenuEventType = QEvent.Type(QEvent.registerEventType())
    MpvShutdownEventType = QEvent.Type(QEvent.registerEventType())
    MpvOpenDialogEventType = QEvent.Type(QEvent.registerEventType())

    MpvCryptoEventType = QEvent.Type(QEvent.registerEventType())


class CryptoType(Enum):
    timeout = 0
    nokey = 1


class MpvCryptoEvent(QEvent):

    def __init__(self, crypto_type: CryptoType, type: QEvent.Type) -> None:
        super().__init__(type)
        self.crypto_type = crypto_type


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
        self.pop_menu.popup(QPoint(20000, 10000))
        self.pop_menu.close()

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

        return {
            open_local_file_act.name: open_local_file_act,
            add_local_file_act.name: add_local_file_act,
            open_key_mgr_act.name: open_key_mgr_act
        }

    def _create_menus(self):
        pop_menu = QMenu()
        pop_menu.setContextMenuPolicy(Qt.CustomContextMenu)
        pop_menu.addAction(self.menu_actions['open_local_file_act'].action)
        pop_menu.addAction(self.menu_actions['add_local_file_act'].action)
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
                 func: Callable):
        self.name = name
        self.action = action
        self.func = func
