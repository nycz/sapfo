#!/usr/bin/env python3

import collections
from operator import itemgetter
import os
import os.path
from os.path import join
import re
import shutil
import sys

from PyQt4 import QtGui, QtWebKit
from PyQt4.QtCore import Qt, QEvent

from libsyntyche import common
from terminal import Terminal
from indexframe import IndexFrame
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self, profile):
        super().__init__()
        self.setWindowTitle('Sapfo')

        # Create layouts
        self.stack = QtGui.QStackedLayout(self)
        common.kill_theming(self.stack)
        self.index_widget = QtGui.QWidget(self)
        layout = QtGui.QVBoxLayout(self.index_widget)
        common.kill_theming(layout)

        # Index viewer
        self.index_viewer = IndexFrame(self.index_widget)
        layout.addWidget(self.index_viewer, stretch=1)

        # Terminal
        self.terminal = Terminal(self.index_widget)
        layout.addWidget(self.terminal)

        # Add both to stack
        self.stack.addWidget(self.index_widget)

        # Story viewer
        self.story_viewer = ViewerFrame(self)
        self.stack.addWidget(self.story_viewer)

        # Load profile
        self.profile = profile
        self.reload_settings()

        # Misc
        self.connect_signals()
        self.set_stylesheet()
        self.show()

    def connect_signals(self):
        t, iv = self.terminal, self.index_viewer
        connects = (
            (t.filter_,                 iv.filter_entries),
            (t.sort,                    iv.sort_entries),
            (t.find_open,               iv.find_entry),
            (t.open_,                   iv.open_entry),
            (t.edit,                    iv.edit_entry),
            (t.input_term.scroll_index, iv.event),
            (t.reload_settings,         self.reload_settings),
            (self.story_viewer.show_index, self.show_index),
            (iv.start_entry,            self.start_entry),
            (iv.error,                  t.error),
            (iv.set_terminal_text,      t.input_term.setText)
        )
        for signal, slot in connects:
            signal.connect(slot)

    def show_index(self):
        self.stack.setCurrentWidget(self.index_widget)
        self.terminal.setFocus()


    def start_entry(self, entry):
        self.story_viewer.start(entry)
        self.stack.setCurrentWidget(self.story_viewer)


    def reload_settings(self):
        settings = read_config()
        if not self.profile:
            self.profile = settings['default profile']
        if self.profile not in settings['profiles']:
            raise NameError('Profile not found')
        profile_settings = update_dict(settings['default settings'],
                                       settings['profiles'][self.profile])
        self.index_viewer.update_settings(profile_settings)
        self.story_viewer.set_hotkeys(profile_settings['hotkeys'])


    def set_stylesheet(self):
        self.setStyleSheet(common.parse_stylesheet(\
                           common.read_file(common.local_path('qt.css'))))


    # ===== Input overrides ===========================
    def wheelEvent(self, ev):
        self.index_viewer.wheelEvent(ev)

    def keyPressEvent(self, ev):
        if self.stack.currentWidget() == self.index_widget and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.keyPressEvent(ev)
        else:
            return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if self.stack.currentWidget() == self.index_widget and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.keyReleaseEvent(ev)
        else:
            return super().keyReleaseEvent(ev)
    # =================================================



def read_config():
    config_file = os.path.join(os.getenv('HOME'), '.config', 'sapfo', 'settings.json')
    common.make_sure_config_exists(config_file, common.local_path('default_settings.json'))
    return common.read_json(config_file)


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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', nargs='?')
    args = parser.parse_args()

    app = QtGui.QApplication(sys.argv)
    window = MainWindow(args.profile)
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
