import os
from typing import List
from io import BytesIO
from urllib.parse import urlparse, parse_qs
import platform

from keymanager.encryptor import encrypt_data1, decrypt_data1
from gxbzys.mpv import (
    MPV, register_protocol,
    StreamOpenFn, StreamCloseFn, StreamReadFn, StreamSeekFn, StreamSizeFn
)


BLOCK_SIZE = 1024 * 1024
HEAD_FILE_MARKER = b'EV00001'

HEAD_FILE_MARKER_LEN = 7
HEAD_BLOCK_SIZE_LEN = 3
HEAD_RAW_FILE_LEN = 5
HEAD_HEAD_PART_LEN = 4
HEAD_IV_LEN = 16

HEAD_VIDEO_BLOCK_INFO_LEN = \
    HEAD_IV_LEN + HEAD_RAW_FILE_LEN * 2 + HEAD_BLOCK_SIZE_LEN * 2

EMPTY_IV = b'\0' * 16


class VideoBlockInfo:

    def __init__(self,
                 iv: bytes = EMPTY_IV,
                 data_size: int = 0,
                 start_pos: int = 0,
                 raw_start_pos: int = 0,
                 block_size: int = 0):
        self.iv = iv
        self.start_pos = start_pos
        self.raw_start_pos = raw_start_pos
        self.data_size = data_size  # 数据长度
        self.block_size = block_size  # 加密以后的长度

    def read_block_data(self, input_stream):
        input_stream.seek(self.start_pos)
        return input_stream.read(self.block_size)

    def to_bytes(self):
        bos = BytesIO()

        b_iv = self.iv
        b_start_pos = self.start_pos.to_bytes(HEAD_RAW_FILE_LEN, byteorder='big')
        b_raw_start_pos = self.raw_start_pos.to_bytes(HEAD_RAW_FILE_LEN, byteorder='big')
        b_data_size = self.data_size.to_bytes(HEAD_BLOCK_SIZE_LEN, byteorder='big')
        b_block_size = self.block_size.to_bytes(HEAD_BLOCK_SIZE_LEN, byteorder='big')

        bos.write(b_iv)  # 16
        bos.write(b_start_pos)  # 5
        bos.write(b_raw_start_pos)  # 5
        bos.write(b_data_size)  # 3
        bos.write(b_block_size)  # 3
        bos.seek(0)

        buffer = bos.read()
        return buffer  # 32

    @staticmethod
    def from_bytes(data):
        bis = BytesIO(data)
        vbi = VideoBlockInfo()

        b_iv = bis.read(HEAD_IV_LEN)
        b_start_pos = bis.read(HEAD_RAW_FILE_LEN)
        b_raw_start_pos = bis.read(HEAD_RAW_FILE_LEN)
        b_data_size = bis.read(HEAD_BLOCK_SIZE_LEN)
        b_block_size = bis.read(HEAD_BLOCK_SIZE_LEN)

        vbi.iv = b_iv
        vbi.start_pos = int.from_bytes(b_start_pos, byteorder='big')
        vbi.raw_start_pos = int.from_bytes(b_raw_start_pos, byteorder='big')
        vbi.data_size = int.from_bytes(b_data_size, byteorder='big')
        vbi.block_size = int.from_bytes(b_block_size, byteorder='big')
        return vbi


class VideoHead:

    def __init__(self):
        self.block_index: List[VideoBlockInfo] = []
        self.head_size = 0
        self.raw_file_size = 0

    def update_head_size(self):
        self.head_size = \
            HEAD_FILE_MARKER_LEN + HEAD_HEAD_PART_LEN + HEAD_RAW_FILE_LEN \
            + len(self.block_index) * HEAD_VIDEO_BLOCK_INFO_LEN

    def to_bytes(self):

        self.update_head_size()

        bos = BytesIO()
        bos.write(HEAD_FILE_MARKER)  # 7
        bos.write(self.head_size.to_bytes(HEAD_HEAD_PART_LEN, byteorder='big'))  # 4
        bos.write(self.raw_file_size.to_bytes(HEAD_RAW_FILE_LEN, byteorder='big'))  # 5
        for vbi in self.block_index:
            bos.write(vbi.to_bytes())  # 32

        return bos.getvalue()

    @staticmethod
    def get_head_block(reader):
        reader.seek(HEAD_FILE_MARKER_LEN)
        head_size = int.from_bytes(reader.read(HEAD_HEAD_PART_LEN), byteorder='big')
        reader.seek(0)
        return reader.read(head_size)

    @staticmethod
    def from_bytes(data):
        bis = BytesIO(data)
        bis.seek(HEAD_FILE_MARKER_LEN)
        vh = VideoHead()
        vh.head_size = int.from_bytes(bis.read(HEAD_HEAD_PART_LEN), byteorder='big')
        vh.raw_file_size = int.from_bytes(bis.read(HEAD_RAW_FILE_LEN), byteorder='big')
        block_index_size = vh.head_size - (HEAD_FILE_MARKER_LEN + HEAD_HEAD_PART_LEN + HEAD_RAW_FILE_LEN)
        if block_index_size % HEAD_VIDEO_BLOCK_INFO_LEN != 0:
            raise Exception('head size incorrect')
        block_num = int(block_index_size / HEAD_VIDEO_BLOCK_INFO_LEN)
        for idx in range(block_num):
            block_data = bis.read(HEAD_VIDEO_BLOCK_INFO_LEN)
            vbi = VideoBlockInfo.from_bytes(block_data)
            vh.block_index.append(vbi)
        return vh

    @staticmethod
    def from_raw_file(input_file, default_block_size=BLOCK_SIZE):
        file_size = os.path.getsize(input_file)

        vh = VideoHead()
        vh.raw_file_size = file_size
        block_num = int(file_size / default_block_size) + 1

        for _ in range(block_num):
            vbi = VideoBlockInfo()
            vh.block_index.append(vbi)
        return vh


def write_encrypt_video(key, head: VideoHead, input_stream, output_stream, default_block_size=BLOCK_SIZE):
    block_index = head.block_index
    head.update_head_size()
    start_pos = head.head_size
    input_stream.seek(0)
    for i, block in enumerate(block_index):

        block.raw_start_pos = input_stream.tell()
        video_data = input_stream.read(default_block_size)

        iv, enc_data = encrypt_data1(key, video_data)

        block.data_size = len(video_data)
        block.block_size = len(enc_data)
        block.start_pos = start_pos
        block.iv = iv

        start_pos += block.block_size
        output_stream.write(enc_data)


class Stream:

    def __init__(self, file_path: str, key):
        self.file_path = file_path
        self.key = key
        self.head: VideoHead = None
        self.index = 0
        self.block_stream = None
        self.file_stream = None
        self._mpv_callbacks_ = []

    def open(self):
        self.file_stream = open(self.file_path, 'rb')
        head_block = VideoHead.get_head_block(self.file_stream)
        self.head = VideoHead.from_bytes(head_block)
        self.index = 0
        self._open_datablock_stream()

    def close(self):
        if self.file_stream is not None:
            self.file_stream.close()

        if self.block_stream is not None:
            self.block_stream.close()

        self.head: VideoHead = None
        self.index = 0
        self.block_stream = None
        self.file_stream = None

    def read(self, length):
        remaining = length

        data = b''
        while True:
            new_data = self.block_stream.read(remaining)
            remaining = remaining - len(new_data)
            data += new_data

            # 读取了指定长度的数据，返回
            if remaining == 0:
                break

            # 当前数据块已经读完，需要继续读取
            self.index += 1
            if self.index >= len(self.head.block_index):
                break
            self._open_datablock_stream()

        return data

    def seek(self, pos):
        for idx, block in enumerate(self.head.block_index):
            if pos < block.raw_start_pos:
                self.index = idx - 1
                print(' idx:', self.index)
                last_block = self.head.block_index[self.index]
                self._open_datablock_stream()
                self.block_stream.seek(pos - last_block.raw_start_pos)
                break
        return self.block_stream.tell() + self.head.block_index[self.index].raw_start_pos

    def tell(self):
        return self.block_stream.tell() + self.head.block_index[self.index].raw_start_pos

    def _open_datablock_stream(self):
        block = self.head.block_index[self.index]
        enc_data = block.read_block_data(self.file_stream)
        data = decrypt_data1(self.key, block.iv, block.data_size, enc_data)
        if self.block_stream is not None:
            self.block_stream.close()
        self.block_stream = BytesIO(data)


KeyCache = []


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

        key = KeyCache[key_index]

        stream = Stream(file_path, key)
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

