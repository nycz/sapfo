#!/usr/bin/env python3

import collections
import os
import os.path
import shutil
import sys

from PyQt4 import QtGui

from libsyntyche import common
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sapfo')

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.tab_widget = QtGui.QTabWidget(self)
        layout.addWidget(self.tab_widget)

        instances = read_config()
        self.viewerframes = {}
        for name, data in instances.items():
            if name == 'default':
                continue
            newdata = update_dict(instances['default'].copy(), data)
            self.viewerframes[name] = ViewerFrame(name, newdata)
            self.viewerframes[name].set_fullscreen.connect(self.set_fullscreen)
            self.viewerframes[name].request_reload.connect(self.reload)
            self.tab_widget.addTab(self.viewerframes[name], name)

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.reload)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, self.reload)

        self.set_stylesheet()
        self.show()

    def set_fullscreen(self, fullscreen):
        self.tab_widget.tabBar().setHidden(fullscreen)

    def reload(self):
        self.set_stylesheet()
        instances = read_config()
        for name, data in instances.items():
            if name == 'default':
                continue
            newdata = update_dict(instances['default'].copy(), data)
            self.viewerframes[name].reload(newdata)
        # self.tab_widget.currentWidget().reload()

    def set_stylesheet(self):
        self.setStyleSheet(common.parse_stylesheet(\
                           common.read_file(common.local_path('qt.css'))))

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

def read_config():
    config_dir = os.path.join(os.getenv('HOME'), '.config', 'sapfo')
    config_file = os.path.join(config_dir, 'settings.json')
    if not os.path.exists(config_file):
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, mode=0o755, exist_ok=True)
        shutil.copyfile(common.local_path('default_settings.json'), config_file)
        print("No config found, copied the default to {}. Edit it at once.".format(config_dir))
    return common.read_json(config_file)


def main():
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
