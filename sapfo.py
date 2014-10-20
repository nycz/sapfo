#!/usr/bin/env python3

import collections
import copy
from os import getenv
from os.path import isdir, join
import sys

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from libsyntyche import common
from terminal import Terminal
from indexframe import IndexFrame
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self, configdir, activation_event):
        super().__init__()
        self.setWindowTitle('Sapfo')
        self.configdir = configdir
        activation_event.connect(self.reload_settings)

        # Create layouts
        self.stack = QtGui.QStackedLayout(self)
        common.kill_theming(self.stack)
        self.index_widget = QtGui.QWidget(self)
        layout = QtGui.QVBoxLayout(self.index_widget)
        common.kill_theming(layout)

        # Index viewer
        self.index_viewer = IndexFrame(self.index_widget)
        layout.addWidget(self.index_viewer, stretch=1)
        self.popup = False

        # Terminal
        self.terminal = Terminal(self.index_widget, self.index_viewer.get_tags)
        layout.addWidget(self.terminal)

        # Add both to stack
        self.stack.addWidget(self.index_widget)

        # Story viewer
        self.story_viewer = ViewerFrame(self)
        self.stack.addWidget(self.story_viewer)

        # Load settings
        self.css_template = common.read_file(common.local_path('template.css'))
        self.index_css_template = common.read_file(common.local_path('index_page.css'))
        self.viewer_css_template = common.read_file(common.local_path('viewer_page.css'))
        self.settings, self.style = {}, {}
        self.reload_settings()

        # Misc
        self.connect_signals()
        self.show()

    def connect_signals(self):
        t, iv = self.terminal, self.index_viewer
        connects = (
            (t.filter_,                 iv.filter_entries),
            (t.sort,                    iv.sort_entries),
            (t.open_,                   iv.open_entry),
            (t.edit,                    iv.edit_entry),
            (t.input_term.scroll_index, iv.event),
            (t.list_,                   iv.list_),
            (t.count_length,            iv.count_length),
            (t.external_edit,           iv.external_run_entry),
            (t.reload_settings,         self.reload_settings),
            (self.story_viewer.show_index, self.show_index),
            (t.quit,                    self.close),
            (iv.view_entry,             self.view_entry),
            (iv.error,                  t.error),
            (iv.print_,                 t.print_),
            (iv.init_popup,             self.popup_mode),
            (iv.set_terminal_text,      t.prompt)
        )
        for signal, slot in connects:
            signal.connect(slot)


    def show_index(self):
        self.stack.setCurrentWidget(self.index_widget)
        self.terminal.setFocus()


    def view_entry(self, entry):
        self.story_viewer.view_page(entry)
        self.stack.setCurrentWidget(self.story_viewer)


    def popup_mode(self):
        self.popup = 2


    def reload_settings(self):
        settings, style = read_config(self.configdir)
        # TODO: FIX THIS UGLY ASS SHIT
        # Something somewhere fucks up and changes the settings dict,
        # therefor the deepcopy(). Fix pls.
        if settings != self.settings:
            self.settings = copy.deepcopy(settings)
            self.index_viewer.update_settings(settings)
            self.story_viewer.set_hotkeys(settings['hotkeys'])
            self.story_viewer.formatconverters = settings['formatting converters']
        if style != self.style:
            self.style = copy.deepcopy(style)
            self.update_style(style)


    def update_style(self, style):
        try:
            css = self.css_template.format(**style)
            indexcss = self.index_css_template.format(**style)
            viewercss = self.viewer_css_template.format(**style)
        except KeyError as e:
            print(e)
            self.terminal.error('Invalid style config: key missing')
            return
        self.setStyleSheet(css)
        self.index_viewer.css = indexcss
        self.story_viewer.css = viewercss
        self.index_viewer.refresh_view(keep_position=True)
        if self.story_viewer.isEnabled():
            self.story_viewer.update_css()


    # ===== Input overrides ===========================
    def wheelEvent(self, ev):
        self.index_viewer.wheelEvent(ev)

    def keyPressEvent(self, ev):
        if self.stack.currentWidget() == self.index_widget and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.keyPressEvent(ev)
        else:
            if self.popup:
                if ev.key() == Qt.Key_Return:
                    if self.popup > 1:
                        self.popup -= 1
                    else:
                        self.index_viewer.close_popup()
                        self.popup = False
            else:
                return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if self.stack.currentWidget() == self.index_widget and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.keyReleaseEvent(ev)
        else:
            if not self.popup:
                return super().keyReleaseEvent(ev)
    # =================================================


def read_config(configdir):
    if configdir:
        configpath = configdir
    else:
        configpath = join(getenv('HOME'), '.config', 'sapfo')
    configfile = join(configpath, 'settings.json')
    stylefile = join(configpath, 'style.json')
    common.make_sure_config_exists(configfile, common.local_path('default_settings.json'))
    common.make_sure_config_exists(stylefile, common.local_path('defaultstyle.json'))
    return common.read_json(configfile), common.read_json(stylefile)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    def valid_dir(dirname):
        if isdir(dirname):
            return dirname
        parser.error('Directory does not exist: {}'.format(dirname))
    parser.add_argument('-c', '--config-directory', type=valid_dir)
    args = parser.parse_args()

    app = QtGui.QApplication(sys.argv)

    class AppEventFilter(QtCore.QObject):
        activation_event = QtCore.pyqtSignal()
        def eventFilter(self, object, event):
            if event.type() == QtCore.QEvent.ApplicationActivate:
                self.activation_event.emit()
            return False
    app.event_filter = AppEventFilter()
    app.installEventFilter(app.event_filter)

    window = MainWindow(args.config_directory, app.event_filter.activation_event)
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
