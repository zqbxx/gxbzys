import sys

from PySide2.QtCore import QThread, Signal, Qt, QTextStream
from PySide2.QtGui import QPalette, QColor
from PySide2.QtWidgets import QApplication
import os
os.environ['QT_API'] = 'PySide2'
from gxbzys.dialogs import KeyMgrDialog
from PySide2.QtCore import QFile

os.environ["PATH"] = '.' + os.pathsep + os.environ["PATH"]
from keymanager import iconic
from gxbzys.player import SMPVPlayer
from keymanager import utils as kmutils


if __name__ == "__main__":

    #kmutils.ICON_COLOR['color'] = '#8a949a'
    kmutils.ICON_COLOR['color'] = '#a3cfd4'
    #kmutils.ICON_COLOR['color'] = '#1caab8'

    kmutils.ICON_COLOR['active'] = 'black'

    app = QApplication([])
    app.setApplicationName("播放器")

    import qtmodern.styles
    import qtmodern.windows
    qtmodern.styles.dark(app)

    QApplication.setQuitOnLastWindowClosed(False)
    smpv_player = SMPVPlayer()
    smpv_player.start()

    sys.exit(app.exec_())
