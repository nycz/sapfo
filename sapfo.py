#!/usr/bin/env python3

import copy
from os import getenv
from os.path import isdir, join
import sys

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt

from libsyntyche.common import read_json, read_file, local_path, make_sure_config_exists
from libsyntyche.fileviewer import FileViewer
from indexframe import IndexFrame
from viewerframe import ViewerFrame
from backstorywindow import BackstoryWindow


class MainWindow(QtWidgets.QWidget):
    def __init__(self, configdir, activation_event, dry_run):
        super().__init__()
        self.setWindowTitle('Sapfo')
        if configdir:
            self.configdir = configdir
        else:
            self.configdir = join(getenv('HOME'), '.config', 'sapfo')
        activation_event.connect(self.reload_settings)
        self.force_quit_flag = False

        # Create layouts
        self.stack = QtWidgets.QStackedLayout(self)

        # Index viewer
        self.index_viewer = IndexFrame(self, dry_run, join(self.configdir, 'state'))
        self.stack.addWidget(self.index_viewer)

        # Story viewer
        self.story_viewer = ViewerFrame(self)
        self.stack.addWidget(self.story_viewer)

        # Backstory editor
        self.backstorywindows = {}

        # Popup viewer
        self.popup_viewer = FileViewer(self)
        self.stack.addWidget(self.popup_viewer)
        self.popuphomekey = QtWidgets.QShortcut(QtGui.QKeySequence(),
                                            self.popup_viewer,
                                            self.show_index)

        # Load settings
        self.css_parts = ['qt', 'index_page', 'viewer_page']
        self.css_overrides = {x: '' for x in self.css_parts}
        self.css = {x: read_file(local_path(join('templates', '{}.css'.format(x))))
                    for x in self.css_parts}
        self.settings = {}
        self.reload_settings()

        # Misc
        self.connect_signals()
        self.show()

    def closeEvent(self, event):
        # Don't quit if any backstory windows are open
        if self.backstorywindows:
            self.index_viewer.terminal.error('One or more backstory windows are still open!')
            event.ignore()
        else:
            event.accept()

    def quit(self, force):
        # This flag is not used atm
        self.force_quit_flag = force
        self.close()

    def connect_signals(self):
        connects = (
            (self.story_viewer.show_index,  self.show_index),
            (self.index_viewer.quit,        self.close),
            (self.index_viewer.view_entry,  self.view_entry),
            (self.index_viewer.view_meta,   self.open_backstory_editor),
            (self.index_viewer.show_popup,  self.show_popup),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def show_index(self):
        self.stack.setCurrentWidget(self.index_viewer)
        self.index_viewer.terminal.setFocus()

    def view_entry(self, entry):
        self.story_viewer.view_page(entry)
        self.stack.setCurrentWidget(self.story_viewer)

    def open_backstory_editor(self, entry):
        if entry.file in self.backstorywindows:
            self.backstorywindows[entry.file].activateWindow()
            self.backstorywindows[entry.file].raise_()
            return
        bsw = BackstoryWindow(entry, self.settings)
        bsw.setStyleSheet(self.styleSheet())
        self.backstorywindows[entry.file] = bsw
        bsw.closed.connect(self.forget_backstory_window)

    def forget_backstory_window(self, file):
        bsw = self.backstorywindows[file]
        bsw.deleteLater()
        del self.backstorywindows[file]

    def show_popup(self, *args):
        self.popup_viewer.set_page(*args)
        self.stack.setCurrentWidget(self.popup_viewer)

    def reload_settings(self):
        settings, css_overrides = read_config(self.configdir, self.css_parts)
        # TODO: FIX THIS UGLY ASS SHIT
        # Something somewhere fucks up and changes the settings dict,
        # therefor the deepcopy(). Fix pls.
        if settings != self.settings:
            if settings['title']:
                self.setWindowTitle(settings['title'])
            else:
                self.setWindowTitle('Sapfo')
            self.settings = copy.deepcopy(settings)
            self.index_viewer.update_settings(settings)
            self.story_viewer.update_settings(settings)
            for bsw in self.backstorywindows.values():
                bsw.update_settings(settings)
            self.popuphomekey.setKey(QtGui.QKeySequence(settings['hotkeys']['home']))
        # if self.css_overrides != css_overrides:
        self.update_style(css_overrides)


    def update_style(self, css_overrides):
        css = self.css['qt'] + '\n' + css_overrides['qt']
        self.setStyleSheet(css)
        for bsw in self.backstorywindows.values():
            bsw.setStyleSheet(css)
        self.index_viewer.css = self.css['index_page'] + '\n' + css_overrides['index_page']
        self.story_viewer.css = self.css['viewer_page'] + '\n' + css_overrides['viewer_page']
        self.index_viewer.refresh_view(keep_position=True)
        if self.story_viewer.isEnabled():
            self.story_viewer.update_css()
        self.css_overrides = css_overrides


    # ===== Input overrides ===========================
    def keyPressEvent(self, ev):
        if self.stack.currentWidget() == self.index_viewer and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.webview.keyPressEvent(ev)
        else:
            return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if self.stack.currentWidget() == self.index_viewer and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.webview.keyReleaseEvent(ev)
        else:
            return super().keyReleaseEvent(ev)
    # =================================================


def read_config(configpath, cssnames):
    configfile = join(configpath, 'settings.json')
    styles = {}
    for name in cssnames:
        fullpath = join(configpath, '{}.css'.format(name))
        try:
            data = read_file(fullpath)
        except:
            data = ''
        finally:
            styles[name] = data
    make_sure_config_exists(configfile, local_path('defaultconfig.json'))
    return read_json(configfile), styles


def main():
    import argparse
    parser = argparse.ArgumentParser()
    def valid_dir(dirname):
        if isdir(dirname):
            return dirname
        parser.error('Directory does not exist: {}'.format(dirname))
    parser.add_argument('-c', '--config-directory', type=valid_dir)
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='don\'t write anything to disk')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)

    class AppEventFilter(QtCore.QObject):
        activation_event = QtCore.pyqtSignal()
        def eventFilter(self, object, event):
            if event.type() == QtCore.QEvent.ApplicationActivate:
                self.activation_event.emit()
            return False
    app.event_filter = AppEventFilter()
    app.installEventFilter(app.event_filter)

    window = MainWindow(args.config_directory,
                        app.event_filter.activation_event,
                        args.dry_run)
    app.setActiveWindow(window)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
