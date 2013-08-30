import os.path

from PyQt4 import QtCore, QtGui

from libsyntyche import common


class InfoPanel(QtGui.QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        layout = QtGui.QGridLayout(self)
        common.kill_theming(layout)

        class InfoPanelLabel(QtGui.QLabel): pass
        self.label = InfoPanelLabel()
        layout.addWidget(self.label, 0, 0, QtCore.Qt.AlignHCenter)

        self.show()

    def set_info(self, page_list, index):
        s = "<em>Page</em> {page}/{maxpages}\t–\t<strong>File</strong>: {fname}"
        if page_list[index][1]:
            s += "\t–\tChapter: {}".format(page_list[index][1])
        self.label.setText(s.format(
            page=index+1,
            maxpages=len(page_list),
            fname=os.path.basename(page_list[index][0]))
        )

    def set_fullscreen(self, fullscreen):
        self.setHidden(fullscreen)
