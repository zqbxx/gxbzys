import os
from io import BytesIO, FileIO
from typing import List, Iterator
from unittest import TestCase

from gxbzys.video import VideoHead, write_encrypt_video, VideoStream, VideoInfo, VideoInfoIndex
from keymanager.utils import write_file, read_file


class TestWrite_encrypt_video(TestCase):

    def test_write_video_info_index(self):
        input_file = './data/photo-1615529328331-f8917597711f.enc.webp'

        head: VideoHead = VideoHead.from_raw_file(input_file, default_block_size=1024)
        video_info_list: List[VideoInfoIndex] = []
        video_info_list.append(VideoInfoIndex(100))
        video_info_list.append(VideoInfoIndex(200))
        video_info_list.append(VideoInfoIndex(300))
        head.video_info_index = video_info_list
        head.update_head_size()

        head_bytes = head.to_bytes()
        try:
            new_head = VideoHead.from_bytes(head_bytes)
        except Exception as e:
            new_head = e.args[1]
        assert new_head.video_info_index_size == head.video_info_index_size
        assert head.head_size == new_head.head_size
        assert head.raw_file_size == new_head.raw_file_size

        assert len(head.video_info_index) == 3
        assert head.video_info_index[0].length == 100
        assert head.video_info_index[1].length == 200
        assert head.video_info_index[2].length == 300

    def test_write_encrypt_video(self):
        default_block_size = 1024
        input_file = './enc/photo-1615529328331-f8917597711f.webp'
        output_file = './enc/photo-1615529328331-f8917597711f.enc.webp'
        key_file = './enc/key.key'

        # 生成密钥
        head: VideoHead = VideoHead.from_raw_file(input_file, default_block_size=default_block_size)
        key = os.urandom(32)
        write_file(key_file, key)

        reader = open(input_file, 'rb')
        writer = open(output_file, 'wb')

        # 加入视频信息
        file_list_1 = ['./data/icons/Apple.png',
                       './data/icons/Facebook.png',
                       './data/icons/Linkedin.png',
                       './data/icons/Tiktok.png',
                       './data/icons/Twitter.png']

        file_list_2 = ['./data/icons/bell.png',
                       './data/icons/camera.png']

        file_list = [file_list_1, file_list_2]
        video_info_list = []
        for f_list in file_list:
            video_info = VideoInfo()
            for f in f_list:
                _, file = os.path.split(f)
                name, ext = os.path.splitext(file)
                video_info.add_info(name.encode('utf-8'), read_file(f))
            video_info_list.append(video_info)

        def videowritehook(current, total):
            print(f'write video block {current}, total: {total}')

        # 写入加密数据
        write_encrypt_video(key, head, video_info_list, reader, writer, default_block_size=default_block_size, videowritehook=videowritehook)
        writer.close()
        reader.close()

        # 校验
        print('block num:', len(head.block_index))
        print('head size:', head.head_size)
        print('info index size:', head.video_info_index_cnt * VideoInfoIndex.video_info_index_len)

        print('output file size: ', os.path.getsize(output_file))
        print('input file size: ', os.path.getsize(input_file))

        assert head.file_size == os.path.getsize(output_file)

        reader = open(output_file, 'rb')
        head_bytes = VideoHead.get_head_block(reader)
        new_head: VideoHead = VideoHead.from_bytes(head_bytes)
        reader.close()
        assert head.head_size == new_head.head_size
        assert head.raw_file_size == new_head.raw_file_size
        assert head.video_info_index_size == new_head.video_info_index_size
        assert head.file_size == new_head.file_size

        for i, video_info in enumerate(head.video_info_index):
            print(f'video info {i} length: {new_head.video_info_index[i].length}')
            assert new_head.video_info_index[i].length == video_info.length
            assert new_head.video_info_index[i].iv == video_info.iv

        all_block_len = 0
        for i in range(len(head.block_index)):
            print(f'check block {i}')
            b1 = head.block_index[i]
            b2 = new_head.block_index[i]
            assert b1.data_size == b2.data_size
            assert b1.start_pos == b2.start_pos
            assert b1.raw_start_pos == b2.raw_start_pos
            assert b1.block_size == b2.block_size
            assert b1.iv.hex() == b2.iv.hex()
            all_block_len += b1.block_size
        print(f'all block length: {all_block_len}')

    def test_seek(self):
        root = r'./data/'
        key_file = os.path.join(root, 'key.key')
        raw_file = os.path.join(root, 'photo-1615529328331-f8917597711f.webp')
        enc_file = os.path.join(root, 'photo-1615529328331-f8917597711f.enc.webp')
        key = read_file(key_file)

        stream = VideoStream(enc_file, key)
        stream.open()
        file_size = stream.head.raw_file_size

        assert file_size == os.stat(raw_file).st_size

        reader = open(raw_file, 'rb')

        def read_and_assert(r1, r2, count):
            d1 = r1.read(count)
            d2 = r2.read(count)
            assert d1.hex() == d2.hex()

        def seek(r1, r2, pos):
            r1.seek(pos)
            r2.seek(pos)

        read_and_assert(stream, reader, 32)
        read_and_assert(stream, reader, 10)
        read_and_assert(stream, reader, 1024)

        seek(stream, reader, 10)

        read_and_assert(stream, reader, 1024)
        print('---')
        seek(stream, reader, 3000)

        read_and_assert(stream, reader, 3000)
        seek(stream, reader, 24000)
        read_and_assert(stream, reader, 30000)
        seek(stream, reader, 10)
        read_and_assert(stream, reader, 5000)

        video_info_reader = stream.video_info_reader
        video_info_reader.open()
        video_info_list = []
        for video_info in video_info_reader.read():
            video_info_list.append(video_info)

        file_list_1 = ['./data/icons/Apple.png',
                       './data/icons/Facebook.png',
                       './data/icons/Linkedin.png',
                       './data/icons/Tiktok.png',
                       './data/icons/Twitter.png']

        file_list_2 = ['./data/icons/bell.png',
                       './data/icons/camera.png']

        file_list = [file_list_1, file_list_2]
        video_info_list_1 = []
        for f_list in file_list:
            video_info = VideoInfo()
            for f in f_list:
                _, file = os.path.split(f)
                name, ext = os.path.splitext(file)
                video_info.add_info(name.encode('utf-8'), read_file(f))
            video_info_list_1.append(video_info)

        for i, video_info in enumerate(video_info_list):
            assert video_info.to_bytes().hex() == video_info_list_1[i].to_bytes().hex()
        video_info_reader.close()
        stream.close()
        reader.close()

    def test_read(self):
        root = r'./data/'
        key_file = os.path.join(root, 'key.key')
        raw_file = os.path.join(root, 'photo-1615529328331-f8917597711f.webp')
        enc_file = os.path.join(root, 'photo-1615529328331-f8917597711f.enc.webp')
        key = read_file(key_file)

        stream = VideoStream(enc_file, key)
        stream.open()
        bos = BytesIO()
        while True:
            data = stream.read(1024 * 5)
            if len(data) == 0:
                break
            bos.write(data)
        stream.close()
        bos.seek(0)
        de_content = bos.read()
        raw_content = read_file(raw_file)
        print(f'解密后大小：{len(de_content)}')
        print(f'文件大小：{len(raw_content)}')
        assert de_content.hex() == raw_content.hex()

    def test_video_info(self):
        vi = VideoInfo()
        name_bytes = b'testvideo.mkv'
        vi.add_info(b'name', name_bytes)
        file_content = read_file('./data/photo-1615529328331-f8917597711f.webp')
        vi.add_info(b'thumbnail0', file_content)
        vi.add_info(b'thumbnail1', BytesIO(file_content))
        vi.add_info(b'thumbnail2', FileIO('./data/photo-1615529328331-f8917597711f.webp'))
        video_info_data = vi.to_bytes()
        new_vi = vi.from_bytes(video_info_data)
        assert vi.video_info_cnt == 4
        assert vi.video_info_cnt == new_vi.video_info_cnt
        assert vi.info[b'name'].hex() == new_vi.info[b'name'].hex()
        assert file_content.hex() == new_vi.info[b'thumbnail0'].hex()
        assert file_content.hex() == new_vi.info[b'thumbnail1'].hex()
        assert file_content.hex() == new_vi.info[b'thumbnail2'].hex()

    def test_video_info_index(self):

        video_info_index = VideoInfoIndex(1024*8)
        video_info_index.iv = os.urandom(16)
        data = video_info_index.to_bytes()
        new_video_info_index = VideoInfoIndex.from_bytes(data)
        assert new_video_info_index.length == video_info_index.length
        assert new_video_info_index.iv == video_info_index.iv

