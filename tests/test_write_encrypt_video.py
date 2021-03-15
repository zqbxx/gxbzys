import os
from unittest import TestCase

from gxbzys.video import VideoHead, write_encrypt_video, Stream
from keymanager.utils import write_file, read_file


class TestWrite_encrypt_video(TestCase):

    def test_write_encrypt_video(self):
        input_file = './enc/photo-1615529328331-f8917597711f.webp'
        output_file = './enc/photo-1615529328331-f8917597711f.enc.webp'
        key_file = './enc/key.key'
        # 加密
        head: VideoHead = VideoHead.from_raw_file(input_file, default_block_size=1024)
        key = os.urandom(32)
        write_file(key_file, key)
        reader = open(input_file, 'rb')
        writer = open(output_file, 'wb')
        writer.write(head.to_bytes())
        print(f'head end pos {writer.tell()}')
        write_encrypt_video(key, head, reader, writer)
        print(f'body end pos {writer.tell()}')
        writer.seek(0)
        writer.write(head.to_bytes())
        writer.close()
        reader.close()
        print('block num:', len(head.block_index))
        print('head size:', head.head_size)
        print('output file size: ', os.path.getsize(output_file))
        print('input file size: ', os.path.getsize(input_file))

        # 解密后进行比较
        reader = open(output_file, 'rb')
        head_bytes = VideoHead.get_head_block(reader)
        new_head: VideoHead = VideoHead.from_bytes(head_bytes)
        reader.close()
        assert head.head_size == new_head.head_size
        assert head.raw_file_size == new_head.raw_file_size

        print('in block index')
        for i in range(len(head.block_index)):
            b1 = head.block_index[i]
            b2 = new_head.block_index[i]
            assert b1.data_size == b2.data_size
            assert b1.start_pos == b2.start_pos
            assert b1.raw_start_pos == b2.raw_start_pos
            assert b1.block_size == b2.block_size
            assert b1.iv.hex() == b2.iv.hex()

    def test_seek(self):
        root = r'./data/'
        key_file = os.path.join(root, 'key.key')
        raw_file = os.path.join(root, 'photo-1615529328331-f8917597711f.webp')
        enc_file = os.path.join(root, 'photo-1615529328331-f8917597711f.enc.webp')
        key = read_file(key_file)

        stream = Stream(enc_file, key)
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

        read_and_assert(stream, reader, 2000)

        seek(stream, reader, 1000)

        read_and_assert(stream, reader, 10240)

        stream.close()
        reader.close()
