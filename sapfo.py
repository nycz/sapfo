#!/usr/bin/env python3

import collections
import sys

from PyQt4 import QtGui

import common
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sapfo')

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.tab_widget = QtGui.QTabWidget(self)
        layout.addWidget(self.tab_widget)

        def update_dict(basedict, newdict):
            for key, value in newdict.items():
                if isinstance(value, collections.Mapping):
                    subdict = update_dict(basedict.get(key, {}), value)
                    basedict[key] = subdict
                elif isinstance(value, type([])):
                    basedict[key] = list(set(value + basedict.get(key, [])))
                else:
                    basedict[key] = value
            return basedict


        instances = common.read_json('settings.json')
        for name, data in instances.items():
            if name == 'default':
                continue
            newdata = update_dict(instances['default'].copy(), data)
            self.tab_widget.addTab(ViewerFrame(name, newdata), name)

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.reload)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, self.reload)

        self.setStyleSheet(common.read_file('qt.css'))
        self.show()

    def reload(self):
        self.setStyleSheet(common.read_file('qt.css'))
        self.tab_widget.currentWidget().reload()


def main():
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
