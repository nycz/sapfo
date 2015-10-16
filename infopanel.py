from os.path import basename

from PyQt4 import QtCore, QtGui

from libsyntyche.common import kill_theming, set_hotkey


class InfoPanel(QtGui.QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QtGui.QGridLayout(self)
        kill_theming(layout)
        class InfoPanelLabel(QtGui.QLabel): pass
        self.label = InfoPanelLabel()
        layout.addWidget(self.label, 1, 0, QtCore.Qt.AlignHCenter)
        self.show()

    def set_data(self, data):
        wc = "<em>({:,})</em>".format(data.wordcount)
        s = "<strong>{fname}</strong>\t&nbsp;\t{wordcount}"
        self.label.setText(s.format(
            fname=data.title,
            wordcount=wc
        ))

    def set_fullscreen(self, fullscreen):
        self.setHidden(fullscreen)
