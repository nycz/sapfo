from PyQt4 import QtCore, QtGui

from libsyntyche.common import kill_theming


class InfoPanel(QtGui.QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        layout = QtGui.QGridLayout(self)
        kill_theming(layout)

        class InfoPanelLabel(QtGui.QLabel): pass
        self.label = InfoPanelLabel()
        layout.addWidget(self.label, 0, 0, QtCore.Qt.AlignHCenter)

        self.data = {}

        self.show()

    def set_data(self, data=None, pagenr=0):
        if data is not None:
            self.data = data
        wc = ""
        if self.data['count words']:
            wc = "\t\t–\t\t<em>({:,})</em>".format(self.data['length'])
        s = "<em>Page</em> {page}/{maxpages}{wordcount}\t\t–\t\t<strong>{fname}</strong>"
        self.label.setText(s.format(
            page=pagenr+1,
            maxpages=len(self.data['pages']),
            fname=self.data['title'],
            wordcount=wc
        ))

    def set_fullscreen(self, fullscreen):
        self.setHidden(fullscreen)
