
import platform
from math import isclose
from enum import Enum
from typing import List
from urllib.parse import urlparse

from PySide2.QtCore import QEvent, QObject
from PySide2.QtWidgets import QApplication, QFileDialog

from gxbzys import mpv
from gxbzys.mpv import MPV, StreamOpenFn, StreamReadFn, StreamCloseFn, StreamSeekFn, StreamSizeFn, register_protocol
from gxbzys.video import VideoStream
from keymanager.key import KEY_CACHE


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

    def set_option(self, name, value):
        mpv._mpv_set_option_string(self.handle, name.encode('utf-8'), value.encode('utf-8'))

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


class VideoAspect:

    def __init__(self, w, h, mpv: SMPV):
        self.w = w
        self.h = h
        self.mpv = mpv

    def get_aspect(self):
        return self.w / self.h

    def get_display_name(self):
        return f'{self.w}:{self.h}'

    def get_option_value(self):
        return self.get_display_name()

    def set_video_aspect(self):
        self.mpv.set_option('video-aspect-override', self.get_option_value())


class VideoAspects:

    def __init__(self, mpv: SMPV):
        self.mpv = mpv

        self.w = 0
        self.h = 0
        self.dw = 0
        self.dh = 0

        self.predefined: List[VideoAspect] = []

    def add_predefined_aspect(self, width, height):
        for aspect in self.predefined:
            if aspect.w == width and aspect.h == height:
                return
        self.predefined.append(VideoAspect(width, height, self.mpv))

    def is_video_ready(self):
        return self.mpv.video_params is not None

    def update_w_h(self):
        params = self.mpv.video_params
        if params is None:
            return
        self.w = params['w']
        self.h = params['h']
        self.dw = params['dw']
        self.dh = params['dh']

    def get_current_aspect_index(self):
        self.update_w_h()

        current_aspect = VideoAspect(self.dw, self.dh, self.mpv).get_aspect()

        # 遍历预设的比例，找出最相近的比例
        aspect_diff = 100000
        index = -1
        for i, rect in enumerate(self.predefined):
            aspect = rect.get_aspect()
            d = abs(current_aspect - aspect)
            if abs(d) < aspect_diff:
                index = i
                aspect_diff = d

        if not isclose(aspect_diff, 0, abs_tol=0.015):
            return -1

        return index


class VideoRotate:

    def __init__(self, mpv: SMPV):
        self.mpv = mpv

    def rotate_left(self, params=None):
        self.rotate(90, params)

    def rotate_right(self, params=None):
        self.rotate(-90, params)

    def rotate(self, value, params=None):
        if params is None:
            params = self.mpv.video_params
        if params is None:
            return
        current_rotate = int(params['rotate'])
        new_rotate = (current_rotate + value) % 360
        self.mpv.set_option('video-rotate', str(new_rotate))

    def rotate_reset(self, params=None):
        if params is None:
            params = self.mpv.video_params
        if params is None:
            return
        self.mpv.set_option('video-rotate', str(0))


class Track:

    def __init__(self,mpv:SMPV, index: int, id: int, selected: bool, title: str, lang: str, type: str):
        self.mpv = mpv
        self.index = index
        self.id = id
        self.selected = selected
        self.title = title
        self.lang = lang
        self.type = type

    def select(self):
        if self.type == 'audio':
            self.mpv.set_option('aid', str(self.id))
        elif self.type == 'sub':
            self.mpv.set_option('sid', str(self.id))

    def get_display_name(self):
        name = ''
        if self.lang is None:
            name += '未知'
        else:
            name += self.lang
        name += ' - '
        if self.title is None:
            name += '未知'
        else:
            name += self.title
        return name


class Tracks:

    def __init__(self, mpv: SMPV, type: str):
        self.mpv = mpv
        self.type = type

    def get_tracks(self) -> List[Track]:
        track_list = self.mpv.track_list
        ret_list: List[Track] = []
        for index, track in enumerate(track_list):
            if track['type'] == self.type:
                id = track['id']
                selected = track['selected']
                title = None
                lang = None
                if 'title' in track:
                    title = track['title']
                if 'lang' in track:
                    lang = track['lang']
                ret_list.append(Track(self.mpv, index, id, selected, title, lang, self.type))
        return ret_list
