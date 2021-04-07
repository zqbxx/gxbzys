import os
from typing import List, Union, Dict, Callable
from io import BytesIO, FileIO
from typing import TypeVar

from typing.io import IO

from keymanager.encryptor import encrypt_data1, decrypt_data1


BLOCK_SIZE = 1024 * 1024
HEAD_FILE_MARKER = b'EV000001'
EMPTY_IV = b'\0' * 16

VideoContentIndexType = TypeVar("VideoContentIndexType", bound="VideoContentIndex")
VideoHeadType = TypeVar("VideoHeadType", bound="VideoHead")


class VideoContentIndex:

    iv_len = 16  #: 偏移向量占用的字节长度
    start_pos_bytes_len = 5  #: 数据块在加密文件中起始位置的数值占用的字节长度
    raw_start_pos_bytes_len = 5  #: 数据块在原始文件中起始位置的数值占用的字节长度
    data_bytes_cnt_len = 3  #：未加密的数据块大小的数值占用的字节长度
    block_bytes_cnt_len = 3  #：加密以后的数据块大小的数值占用的字节长度

    video_content_index_bytes = (
            iv_len +  # 7
            start_pos_bytes_len +  # 5
            raw_start_pos_bytes_len +  # 5
            data_bytes_cnt_len +  # 3
            block_bytes_cnt_len  # 3
    )

    """
    加密视频文件块索引，保存在VideoHead中
    :param iv: 加密使用的偏移向量
    :param data_size: 未加密的数据块大小
    :param start_pos: 数据块在加密文件中的起始位置
    :param raw_start_pos: 数据块在原始文件中的起始位置
    :param block_size: 加密以后的数据块大小
    """
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
        """将输入流定位到本数据块的起始文职，并从输入流中读取 block_size 指定大小的数据"""
        input_stream.seek(self.start_pos)
        return input_stream.read(self.block_size)

    def to_bytes(self) -> bytes:
        cls = self.__class__
        bos = BytesIO()

        b_iv = self.iv
        b_start_pos = self.start_pos.to_bytes(cls.start_pos_bytes_len, byteorder='big')
        b_raw_start_pos = self.raw_start_pos.to_bytes(cls.raw_start_pos_bytes_len, byteorder='big')
        b_data_size = self.data_size.to_bytes(cls.data_bytes_cnt_len, byteorder='big')
        b_block_size = self.block_size.to_bytes(cls.block_bytes_cnt_len, byteorder='big')

        bos.write(b_iv)  # 16
        bos.write(b_start_pos)  # 5
        bos.write(b_raw_start_pos)  # 5
        bos.write(b_data_size)  # 3
        bos.write(b_block_size)  # 3
        bos.seek(0)

        buffer = bos.read()
        return buffer  # 32

    @classmethod
    def from_bytes(cls, data) -> VideoContentIndexType:
        bis = BytesIO(data)
        vbi = VideoContentIndex()

        b_iv = bis.read(cls.iv_len)
        b_start_pos = bis.read(cls.start_pos_bytes_len)
        b_raw_start_pos = bis.read(cls.raw_start_pos_bytes_len)
        b_data_size = bis.read(cls.data_bytes_cnt_len)
        b_block_size = bis.read(cls.block_bytes_cnt_len)

        vbi.iv = b_iv
        vbi.start_pos = int.from_bytes(b_start_pos, byteorder='big')
        vbi.raw_start_pos = int.from_bytes(b_raw_start_pos, byteorder='big')
        vbi.data_size = int.from_bytes(b_data_size, byteorder='big')
        vbi.block_size = int.from_bytes(b_block_size, byteorder='big')
        return vbi


class VideoHead:

    #TODO 加入加密文件长度字段
    video_marker_bytes_cnt = len(HEAD_FILE_MARKER)  #: 文件标记占用的字节数
    video_file_size_bytes_cnt_len = 5  #: 包括文件标记在内的加密文件字节数量的数值所占用的字节数
    video_head_size_bytes_cnt_len = 4  #: 文件头字节数量的数值所占用的字节数
    video_raw_file_size_bytes_cnt_len = 5  #: 原始文件头字节数量的数值所占用的字节数
    video_info_index_bytes_cnt_len = 5  #: 视频信息索引字节数量的数值所占用的字节数
    video_info_index_cnt_bytes_len = 2  #: 视频信息索引数量的字节数量的数值所占用的字节数

    """
    加密视频文件文件头
    """
    def __init__(self):
        self.file_size = 0  #: 包括文件标记在内的加密文件的大小
        self.head_size = 0  #: 文件头字节数，包含文件头中所有数据，包括head_size变量本身
        self.raw_file_size = 0  #: 未加密的文件字节数
        self.video_info_index_size = 0  #: 视频信息块索引占用字节数
        self.video_info_index_cnt = 0  #: 视频信息块数量
        self.video_info_index: List[VideoInfoIndex] = []  #: 视频信息块索引
        self.block_index: List[VideoContentIndex] = []  #: 加密视频文件块索引

    def update_head_size(self):
        """更新文件头数据"""

        # 计算数据长度
        self.video_info_index_cnt = len(self.video_info_index)
        self.video_info_index_size = self.video_info_index_cnt * VideoInfoIndex.video_info_index_len

        # 重置size，再开始计算
        self.head_size = 0

        self.head_size += self.video_marker_bytes_cnt  #  marker, 8
        self.head_size += self.video_file_size_bytes_cnt_len  # file_size 5
        self.head_size += self.video_head_size_bytes_cnt_len  # head_size, 4
        self.head_size += self.video_raw_file_size_bytes_cnt_len  # raw_file_size, 5
        self.head_size += self.video_info_index_bytes_cnt_len  # video_info_index_size, 5
        self.head_size += self.video_info_index_cnt_bytes_len  # video_info_index_cnt, 2
        self.head_size += self.video_info_index_size  # video_info_index_size
        self.head_size += len(self.block_index) * VideoContentIndex.video_content_index_bytes  # block_index

    def to_bytes(self) -> bytes:

        self.update_head_size()

        bos = BytesIO()
        bos.write(HEAD_FILE_MARKER)  # 8
        bos.write(self.file_size.to_bytes(self.video_file_size_bytes_cnt_len, byteorder='big'))  # 5
        bos.write(self.head_size.to_bytes(self.video_head_size_bytes_cnt_len, byteorder='big'))  # 4
        bos.write(self.raw_file_size.to_bytes(self.video_raw_file_size_bytes_cnt_len, byteorder='big'))  # 5
        bos.write(self.video_info_index_size.to_bytes(self.video_info_index_bytes_cnt_len, byteorder='big'))  # 5
        bos.write(self.video_info_index_cnt.to_bytes(self.video_info_index_cnt_bytes_len, byteorder='big'))  # 2

        for info_index in self.video_info_index:
            bos.write(info_index.to_bytes())  # 20

        for vbi in self.block_index:
            bos.write(vbi.to_bytes())  # 32

        return bos.getvalue()

    @classmethod
    def is_encrypt_video(cls, f: Union[str, IO]) -> bool:
        stream = None
        close = False
        if isinstance(f, str):
            stream = open(f, 'rb')
            close = True
        if isinstance(f, IO):
            stream = f
        b_marker = stream.read(cls.video_marker_bytes_cnt)
        if close:
            stream.close()
        return b_marker.hex() == HEAD_FILE_MARKER.hex()

    @classmethod
    def get_head_block(cls, reader) -> bytes:
        """
        获取文件头数据块
        :param reader: 输入数据流
        :return 包含文件头数据的`bytes`对象

        """
        reader.seek(cls.video_marker_bytes_cnt + cls.video_file_size_bytes_cnt_len)  # 8 + 5
        head_size = int.from_bytes(reader.read(cls.video_head_size_bytes_cnt_len), byteorder='big')
        reader.seek(0)
        return reader.read(head_size)

    @classmethod
    def from_bytes(cls, data) -> VideoHeadType:
        bis = BytesIO(data)
        bis.seek(cls.video_marker_bytes_cnt)  # 8
        vh = VideoHead()
        vh.file_size = int.from_bytes(bis.read(cls.video_file_size_bytes_cnt_len), byteorder='big')  # 5
        vh.head_size = int.from_bytes(bis.read(cls.video_head_size_bytes_cnt_len), byteorder='big')  # 4
        vh.raw_file_size = int.from_bytes(bis.read(cls.video_raw_file_size_bytes_cnt_len), byteorder='big')  # 5
        vh.video_info_index_size = int.from_bytes(bis.read(cls.video_info_index_bytes_cnt_len), byteorder='big')  # 5
        vh.video_info_index_cnt = int.from_bytes(bis.read(cls.video_info_index_cnt_bytes_len), byteorder='big')  # 2
        
        if vh.video_info_index_size > 0:
            for i in range(vh.video_info_index_cnt):
                index_data = bis.read(VideoInfoIndex.video_info_index_len)
                info_index = VideoInfoIndex.from_bytes(index_data)
                vh.video_info_index.append(info_index)

        block_index_size = vh.head_size - (
                cls.video_marker_bytes_cnt +  # 7
                cls.video_file_size_bytes_cnt_len +  # 5
                cls.video_head_size_bytes_cnt_len +  # 4
                cls.video_raw_file_size_bytes_cnt_len +  # 5
                cls.video_info_index_bytes_cnt_len +  # 5
                cls.video_info_index_cnt_bytes_len +  # 2
                vh.video_info_index_size)
        if block_index_size % VideoContentIndex.video_content_index_bytes != 0:
            raise Exception('head size incorrect', vh)
        block_num = int(block_index_size / VideoContentIndex.video_content_index_bytes)
        for idx in range(block_num):
            block_data = bis.read(VideoContentIndex.video_content_index_bytes)
            vbi = VideoContentIndex.from_bytes(block_data)
            vh.block_index.append(vbi)
        return vh

    @classmethod
    def from_raw_file(cls, input_file: str, default_block_size: int = BLOCK_SIZE) -> VideoHeadType:
        """
        从文件中创建`VideoHead`对象
        :param input_file: 文件路径
        :param default_block_size: 数据块字节数，默认为1M
        :return `VideoHead`对象

        """
        file_size = os.path.getsize(input_file)

        vh = VideoHead()
        vh.raw_file_size = file_size
        block_num = int(file_size / default_block_size)
        if file_size % default_block_size != 0:
            block_num += 1

        for _ in range(block_num):
            vbi = VideoContentIndex()
            vh.block_index.append(vbi)

        vh.update_head_size()
        return vh


class VideoInfoException(Exception):
    pass


class VideoInfoIndex:

    video_info_bytes_cnt_len = 4
    video_info_iv_len = 16

    video_info_index_len = video_info_bytes_cnt_len + video_info_iv_len

    def __init__(self, length=0):
        self.length = length
        self.iv = b'\0' * 16

    def to_bytes(self) -> bytes:
        bos = BytesIO()
        bos.write(self.length.to_bytes(self.video_info_bytes_cnt_len, byteorder='big'))
        bos.write(self.iv)
        bos.seek(0)
        return bos.getvalue()

    @classmethod
    def from_bytes(cls, data):
        bis = BytesIO(data)
        video_info_index= VideoInfoIndex()
        video_info_index.length= int.from_bytes(bis.read(cls.video_info_bytes_cnt_len), byteorder='big')
        video_info_index.iv = bis.read(cls.video_info_iv_len)
        return video_info_index


class VideoInfo:

    head_all_info_bytes_cnt_len = 2  # 所有信息数量的数值占用的字节数

    data_bytes_cnt_len = 3  # 信息数据长度的数值占用的字节数
    name_max_length = 1024  # 信息名字最大长度
    data_max_len = pow(2, 3 * 8) - 1  # 信息数据的最大长度

    PAD_DATA = b'\0'

    def __init__(self):
        self.video_info_cnt = 0
        self.info: Dict[bytes, Union[bytes, BytesIO, FileIO]] = {}

    def add_info(self, info_name: bytes, info_data: Union[bytes, BytesIO, FileIO]):
        if len(info_name) > VideoInfo.name_max_length:
            raise VideoInfoException(f'name too long, name should < {VideoInfo.name_max_length}')
        self.info[info_name] = info_data

    def _get_data_length(self, data: Union[bytes, BytesIO, FileIO]) -> int:
        if isinstance(data, bytes):
            return len(data)
        if isinstance(data, BytesIO):
            return len(data.getbuffer())
        if isinstance(data, FileIO):
            return os.stat(data.name).st_size
        raise Exception('Unsupported IO')

    def _load_data(self, data: Union[bytes, BytesIO, FileIO]) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, BytesIO):
            data.seek(0)
            return data.read()
        if isinstance(data, FileIO):
            data.seek(0)
            return data.read()
        raise Exception('Unsupported IO')

    def _close_data(self, data: Union[bytes, BytesIO, FileIO]) -> None:
        if isinstance(data, bytes):
            return
        if isinstance(data, BytesIO):
            data.seek(0)
            return
        if isinstance(data, FileIO):
            data.close()
            return
        raise Exception('Unsupported IO')

    def del_info(self, info_name: bytes):
        del self.info[info_name]

    def update_video_info_cnt(self):
        self.video_info_cnt = len(self.info)

    def to_bytes(self) -> bytes:

        self.update_video_info_cnt()
        bos = BytesIO()
        bos.write(self.video_info_cnt.to_bytes(self.head_all_info_bytes_cnt_len, byteorder='big'))  # 2
        for name in self.info:
            data = self.info[name]
            bos.write(self.pad(name, self.name_max_length))  # 1024
            #bos.write(len(data).to_bytes(self.data_bytes_cnt_len, byteorder='big'))  # 3
            data_len = self._get_data_length(data)
            bos.write(data_len.to_bytes(self.data_bytes_cnt_len, byteorder='big'))  # 3
            loaded_data = self._load_data(data)
            bos.write(loaded_data)  # dynamic
            self._close_data(data)

        bos.seek(0)
        return bos.read()

    def close_all_data_io(self):
        for name in self.info:
            data = self.info[name]
            self._close_data(data)

    def create_video_info_index(self) -> VideoInfoIndex:
        video_info_index = VideoInfoIndex()
        video_info_index.length = self.head_all_info_bytes_cnt_len
        for name in self.info:
            data = self.info[name]
            video_info_index.length += self.name_max_length
            video_info_index.length += self.data_bytes_cnt_len
            video_info_index.length += self._get_data_length(data)
        return video_info_index

    @classmethod
    def from_bytes(cls, data):
        vi = VideoInfo()
        bis = BytesIO(data)
        b_video_info_cnt = bis.read(cls.head_all_info_bytes_cnt_len)
        vi.video_info_cnt = int.from_bytes(b_video_info_cnt, byteorder='big')
        for i in range(vi.video_info_cnt):
            b_name = bis.read(cls.name_max_length)
            b_name = VideoInfo.unpad(b_name)
            b_data_len = bis.read(cls.data_bytes_cnt_len)
            data_len = int.from_bytes(b_data_len, byteorder='big')
            b_data = bis.read(data_len)
            vi.info[b_name] = b_data
        vi.update_video_info_cnt()
        return vi

    @classmethod
    def pad(cls, data: bytes, length: int) -> bytes:
        data_len = len(data)
        pad_len = length - data_len
        if pad_len <= 0:
            return data[:length]
        return pad_len * VideoInfo.PAD_DATA + data

    @classmethod
    def unpad(cls, data:bytes) -> bytes:
        result = bytearray(b'')
        data_array = [b'%c' % i for i in data]
        for b in data_array:
            if b == cls.PAD_DATA:
                continue
            result += b
        return bytes(result)


def write_encrypt_video(key: bytes,
                        head: VideoHead,
                        info_list: List[VideoInfo],
                        input_stream: IO,
                        output_stream: IO,
                        default_block_size=BLOCK_SIZE,
                        videowritehook: Callable[[int, int], None] = None) -> None:
    """
        写加密视频文件

        :param key: 加密使用的密钥
        :param head: 视频头
        :param info_list: 视频信息
        :param input_stream: 原始文件的输入流
        :param output_stream: 目标文件的输出流
        :param default_block_size: 视频文件默认块字节数
        :param videowritehook: 写入文件后调用

    """

    video_info_index = [VideoInfoIndex() for _ in info_list]
    head.video_info_index = video_info_index

    head.update_head_size()
    output_stream.write(head.to_bytes())

    # 写入信息块
    for i, info in enumerate(info_list):
        info_bytes = info.to_bytes()
        iv, enc_info_bytes = encrypt_data1(key, info_bytes)
        head.video_info_index[i].iv = iv
        head.video_info_index[i].length = len(enc_info_bytes)
        output_stream.write(enc_info_bytes)

    # 写入视频内容
    block_index = head.block_index
    start_pos = output_stream.tell()
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
        if videowritehook is not None:
            videowritehook(i, len(block_index))

    head.file_size = output_stream.tell()

    # 头信息更新，重新写入
    output_stream.seek(0)
    output_stream.write(head.to_bytes())


class VideoStream:

    def __init__(self, file_path: str, key):
        self.file_path = file_path
        self.key = key
        self.head: VideoHead = None
        self.index = 0
        self.block_stream = None
        self.file_stream = None
        self._mpv_callbacks_ = []
        self.video_info_reader: VideoInfoReader = None

    def open(self):
        self.file_stream = open(self.file_path, 'rb')
        head_block = VideoHead.get_head_block(self.file_stream)
        self.head = VideoHead.from_bytes(head_block)
        if self.head.video_info_index_size > 0:
            self.video_info_reader = VideoInfoReader(
                self.key,
                self.file_path,
                self.file_stream.tell(),
                self.head.video_info_index_size,
                self.head.video_info_index
            )
            # 计算信息区的总长度
            video_info_length = 0
            for info in self.head.video_info_index:
                video_info_length += info.length
            # 跳过信息区
            self.file_stream.seek(video_info_length, 1)
        self.index = 0
        #TODO open中不读取数据流，在read中读取
        self._open_datablock_stream()

    def close(self):
        if self.file_stream is not None:
            self.file_stream.close()

        if self.video_info_reader is not None:
            self.video_info_reader.close()

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
        # TODO seek中不读取数据块，在read中读取
        for idx, block in enumerate(self.head.block_index):
            if pos >= block.raw_start_pos and pos < block.raw_start_pos + block.data_size:
                # 正好为当前数据块，不需要重新打开
                if self.index != idx:
                    self.index = idx
                    self._open_datablock_stream()
                current_block = self.head.block_index[self.index]
                self.block_stream.seek(pos - current_block.raw_start_pos)
                break
        return self.block_stream.tell() + self.head.block_index[self.index].raw_start_pos

    def tell(self):
        return self.block_stream.tell() + self.head.block_index[self.index].raw_start_pos

    def _open_datablock_stream(self):
        #TODO 当前block保存为self.current_block
        block = self.head.block_index[self.index]
        enc_data = block.read_block_data(self.file_stream)
        data = decrypt_data1(self.key, block.iv, block.data_size, enc_data)
        if self.block_stream is not None:
            self.block_stream.close()
        self.block_stream = BytesIO(data)


class VideoInfoReader:

    def __init__(self,
                 key: bytes,
                 file_path: str,
                 start: int,
                 length: int,
                 video_info_index_list: List[VideoInfoIndex]):
        self.key = key
        self.file_path = file_path
        self.start = start
        self.length = length
        self.video_info_index_list = video_info_index_list
        self.reader = None

    def open(self):
        self.reader = open(self.file_path, 'rb')

    def read(self) -> List[VideoInfo]:
        self.reader.seek(self.start)
        for video_info_index in self.video_info_index_list:
            enc_index_data = self.reader.read(video_info_index.length)
            index_data = decrypt_data1(self.key, video_info_index.iv, -1, enc_index_data)
            video_info = VideoInfo.from_bytes(index_data)
            yield video_info

    def close(self):
        if self.reader is not None:
            self.reader.close()
