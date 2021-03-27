import threading
import os
from pathlib import Path

import qtawesome as qta
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from gxbzys.SimpleWindow import Ui_MainWindow
from gxbzys.dialogs import KeyMgrDialog
from gxbzys.mpv import ShutdownError
from gxbzys.video import SMPV, VideoHead
from keymanager.key import KEY_CACHE


class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)

        self.player: SMPV = None

        self.open_btn.setIcon(qta.icon('fa.play', color='#0099CC'))
        self.keymrg_btn.setIcon(qta.icon('fa5s.key', color='#0099CC'))

        self.open_btn.clicked.connect(self.open)
        self.keymrg_btn.clicked.connect(self.open_keymgr)

        self.setWindowTitle('播放器')

        self.show()

    def open(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open file",
            "",
            "mkv Video (*.mkv);;mp4 Video (*.mp4);;Movie files (*.mov);;All files (*.*)",
        )
        if path:
            path = path.replace('\\', '/')
            if VideoHead.is_encrypt_video(path):
                key = KEY_CACHE.get_cur_key()
                if key is None:
                    QMessageBox.critical(self, '打开失败', '密钥没有加载')
                    return
                if key.timeout:
                    QMessageBox.critical(self, '打开失败', '密钥超时，需要重新加载')
                    return
                path = 'crypto:///' + path
            t = threading.Thread(target=self.open_smpv, kwargs={"file_path": path})
            t.start()

    def open_keymgr(self):
        dialog = KeyMgrDialog()
        dialog.exec()

    def open_smpv(self, file_path):

        if self.player is not None:
            self.player.stop()
            try:
                self.player.wait_for_playback()
            finally:
                self.player.terminate()

        self.player = SMPV(ytdl=True,
                           player_operation_mode='pseudo-gui',
                           autofit='70%',
                           script_opts='osc-layout=bottombar,osc-seekbarstyle=bar,osc-deadzonesize=0,osc-minmousemove=3',
                           input_default_bindings=True,
                           input_vo_keyboard=True,
                           osc=True)

        self.player.play(file_path)

        try:
            self.player.wait_for_playback()
        except:
            pass
        finally:
            self.player.terminate()
            self.player = None


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("播放器")
    app.setStyle("Fusion")

    # Fusion dark palette from https://gist.github.com/QuantumCD/6245215.
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    app.setStyleSheet(
        "QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }"
    )

    window = MainWindow()
    app.exec_()

