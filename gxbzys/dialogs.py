import threading
from typing import Callable
import os

from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog, QMessageBox

import keymanager.dialogs as dialog
from gxbzys.video import VideoHead, VideoInfo, write_encrypt_video, VideoStream
from keymanager.encryptor import encrypt_data, not_encrypt_data

import time


class KeyMgrDialog(dialog.KeyMgrDialog):

    def encrypt_files_action(self):
        item = self.get_selected_item()
        key = item.data()
        ef_dialog = EncryptFileDialog(self)
        ef_dialog.set_key(key)
        ef_dialog.exec_()

    def decrypt_files_action(self):
        item = self.get_selected_item()
        key = item.data()
        df_dialog = DecryptFileDialog(self)
        df_dialog.set_key(key)
        df_dialog.exec_()

    def active_exec(self):
        threading.Thread(target=self._delay_activateWindow).start()
        self.exec_()

    def _delay_activateWindow(self):
        while not self.isVisible():
            time.sleep(0.1)
        self.activateWindow()


class EncryptFileDialog(dialog.EncryptFileDialog):

    def __init__(self,
                 parent=None,
                 win_title='加密文件',
                 before_process: Callable = not_encrypt_data,
                 processor: Callable = encrypt_data,
                 success_msg: str = '加密完成',
                 select_file_dlg_filter: str = 'All Files (*);;Text Files (*.txt)',
                 select_file_dlg_title: str = '选择需要加密的文件',
                 select_output_dir_title: str = '选择输出目录') -> None:
        super().__init__(parent, win_title, before_process, processor, success_msg, select_file_dlg_filter,
                         select_file_dlg_title, select_output_dir_title)
        self.label.setText('视频')

    def showEvent(self, a0: QtGui.QShowEvent) -> None:
        super().showEvent(a0)
        self.activateWindow()

    def do_it(self):
        if not self.check_input():
            return
        pd = QProgressDialog(self)
        pd.setMinimumDuration(10)
        pd.setAutoClose(True)
        pd.setAutoReset(False)
        pd.setLabelText('正在处理')
        pd.setCancelButtonText('取消')
        pd.setRange(0, len(self.file_list) * 100)
        pd.setValue(0)
        pd.setWindowModality(Qt.WindowModal)
        pd.show()

        try:

            file_cnt = len(self.file_list)

            for index, file_path in enumerate(self.file_list):

                if pd.wasCanceled():
                    break

                if os.path.exists(file_path):

                    input_file = file_path
                    _, input_file_name = os.path.split(file_path)
                    output_file = os.path.join(self.output_dir_path, input_file_name)

                    head: VideoHead = VideoHead.from_raw_file(input_file)
                    video_info = VideoInfo()
                    video_info.add_info('name'.encode('utf-8'), input_file_name.encode('utf-8'))

                    reader = open(input_file, 'rb')
                    writer = open(output_file, 'wb')

                    def updater(i, length):
                        percent = int((i+1)/length*100)
                        pd.setValue(index * 100 + percent/2)
                        pd.setLabelText(f'正在处理：{(index+1)} / {file_cnt} 当前文件：{percent/2}%')

                    write_encrypt_video(self.key.key, head, [video_info], reader, writer, videowritehook=updater)
                    writer.close()
                    reader.close()

                    #校验文件
                    bufsize = 8 * 1024
                    file_size = os.stat(output_file).st_size
                    readed_size = 0
                    verify_result = True
                    fp1 = VideoStream(output_file, self.key.key)
                    fp2 = open(input_file, 'rb')
                    fp1.open()

                    try:
                        while True:
                            b1 = fp1.read(bufsize)
                            b2 = fp2.read(bufsize)
                            readed_size += len(b1)
                            if b1 != b2:
                                QMessageBox.critical(pd, '处理失败', f'文件{input_file_name}校验失败')
                                verify_result = False
                                break
                            if not b2:
                                verify_result = True
                                break

                            pd.setLabelText(f'正在处理：{(index + 1)} / {file_cnt} 当前文件：{50 + round((readed_size/file_size)*50)}%')
                            pd.setValue(index * 100 + 50 + (readed_size/file_size)*50)
                    finally:
                        fp2.close()
                        fp1.close()

                    if not verify_result:
                        break


            if not pd.wasCanceled():
                QMessageBox.information(pd, '处理完成', self.success_msg)
            else:
                QMessageBox.information(pd, '已经终止', '用户取消')
        except Exception as e:
            QMessageBox.critical(pd, '处理失败', str(e))
        pd.close()
        self.close()


class DecryptFileDialog(dialog.EncryptFileDialog):

    def __init__(self,
                 parent=None,
                 win_title='解密文件',
                 before_process: Callable = not_encrypt_data,
                 processor: Callable = encrypt_data,
                 success_msg: str = '解密完成',
                 select_file_dlg_filter: str = 'All Files (*);;Text Files (*.txt)',
                 select_file_dlg_title: str = '选择需要解密的文件',
                 select_output_dir_title: str = '选择输出目录') -> None:
        super().__init__(parent, win_title, before_process, processor, success_msg, select_file_dlg_filter,
                         select_file_dlg_title, select_output_dir_title)
        self.label.setText('视频')

    def do_it(self):
        if not self.check_input():
            return
        pd = QProgressDialog(self)
        pd.setMinimumDuration(10)
        pd.setAutoClose(True)
        pd.setAutoReset(False)
        pd.setLabelText('正在处理')
        pd.setCancelButtonText('取消')
        pd.setRange(0, len(self.file_list) * 100)
        pd.setValue(0)
        pd.setWindowModality(Qt.WindowModal)
        pd.show()

        try:

            file_cnt = len(self.file_list)

            for index, file_path in enumerate(self.file_list):

                if pd.wasCanceled():
                    break

                if os.path.exists(file_path):

                    input_file = file_path
                    _, input_file_name = os.path.split(file_path)
                    output_file = os.path.join(self.output_dir_path, input_file_name)

                    reader = VideoStream(input_file, self.key.key)
                    reader.open()
                    file_size = reader.head.raw_file_size

                    writer = open(output_file, 'wb')
                    write_size = 0
                    while True:
                        data = reader.read(1024*1024)
                        if len(data) == 0:
                            break
                        writer.write(data)
                        write_size += len(data)
                        percent = int((write_size + 1) / file_size * 100)
                        pd.setValue(index * 100 + percent)
                        pd.setLabelText(f'正在处理：{(index + 1)} / {file_cnt} 当前文件：{percent}%')

                    writer.close()
                    reader.close()

            if not pd.wasCanceled():
                QMessageBox.information(pd, '处理完成', self.success_msg)
            else:
                QMessageBox.information(pd, '已经终止', '用户取消')
        except Exception as e:
            pass
            QMessageBox.critical(pd, '处理失败', str(e))
        pd.close()
        self.close()
