from os.path import basename

from PyQt4 import QtCore, QtGui

from libsyntyche.common import kill_theming, set_hotkey


class InfoPanel(QtGui.QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        layout = QtGui.QGridLayout(self)
        kill_theming(layout)

        class InfoPanelLabel(QtGui.QLabel): pass
        self.fname_label = InfoPanelLabel()
        self.fname_label.setHidden(True)
        layout.addWidget(self.fname_label, 0, 0, QtCore.Qt.AlignHCenter)
        self.label = InfoPanelLabel()
        layout.addWidget(self.label, 1, 0, QtCore.Qt.AlignHCenter)

        set_hotkey("F6", self, self.toggle_filename)

        self.show()

    def toggle_filename(self):
        self.fname_label.setHidden(self.fname_label.isVisible())


    def set_data(self, data):
        wc = "<em>({:,})</em>".format(data.length)
        s = "<strong>{fname}</strong>\t&nbsp;\t{wordcount}"
        self.label.setText(s.format(
            fname=data.title,
            wordcount=wc
        ))
        self.fname_label.setText(basename(data.file))

    def set_fullscreen(self, fullscreen):
        self.setHidden(fullscreen)
