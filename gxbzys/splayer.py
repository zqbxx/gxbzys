import sys

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QApplication


from gxbzys.smpv import SMPVPlayer
from keymanager import utils as kmutils

if __name__ == "__main__":

    kmutils.ICON_COLOR['color'] = '#8a949a'
    kmutils.ICON_COLOR['active'] = 'black'

    app = QApplication([])
    app.setApplicationName("播放器")
    QApplication.setQuitOnLastWindowClosed(False)

    app.setStyle("Fusion")

    # Fusion dark palette from https://gist.github.com/QuantumCD/6245215.
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(138, 148, 154))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, QColor(138, 148, 154))
    palette.setColor(QPalette.Text, QColor(138, 148, 154))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(138, 148, 154))
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    app.setStyleSheet(
        '''
        QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }

        QMenu::item:selected{
             background-color:#cccccc;
        }
        QListView::item:selected{
            background-color:#cccccc;
        }
        '''
    )
    smpv_player = SMPVPlayer()
    smpv_player.start()

    sys.exit(app.exec())
