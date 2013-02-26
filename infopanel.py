
from PyQt4 import QtCore, QtGui, QtWebKit

class InfoPanel(QtGui.QFrame):
    def __init__(self):
        super().__init__()
        # <- page x/max ->    ***    <- chapter x/max ->
        layout = QtGui.QGridLayout(self)
        layout.setMargin(0)
        layout.setSpacing(0)

        class InfoPanelLabel(QtGui.QLabel): pass
        self.page_label = InfoPanelLabel('<- Page 1/12 ->')
        self.chapter_label = InfoPanelLabel('<- Chapter 1/3 ->')

        layout.addWidget(self.page_label, 0, 0, QtCore.Qt.AlignHCenter)
        # layout.addWidget(QtGui.QLabel('***'), 0, 1, QtCore.Qt.AlignHCenter)
        layout.addWidget(self.chapter_label, 0, 1, QtCore.Qt.AlignHCenter)

