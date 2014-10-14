#!/usr/bin/env python3

import collections
import copy
from os import getenv
from os.path import join
import sys

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from libsyntyche import common
from terminal import Terminal
from indexframe import IndexFrame
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self, profile, activation_event):
        super().__init__()
        self.setWindowTitle('Sapfo')
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

        # Load profile
        self.css_template = common.read_file(common.local_path('template.css'))
        self.index_css_template = common.read_file(common.local_path('index_page.css'))
        self.profile = profile
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
            (iv.start_entry,            self.start_entry),
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


    def start_entry(self, entry):
        self.story_viewer.start(entry)
        self.stack.setCurrentWidget(self.story_viewer)


    def popup_mode(self):
        self.popup = 2


    def reload_settings(self):
        settings, style = read_config()
        # TODO: FIX THIS UGLY ASS SHIT
        # Something somewhere fucks up and changes the settings dict,
        # therefor the deepcopy(). Fix pls.
        if settings != self.settings:
            self.settings = copy.deepcopy(settings)
            if not self.profile:
                self.profile = settings['default profile']
            if self.profile not in settings['profiles']:
                raise NameError('Profile not found')
            profile_settings = update_dict(settings['default settings'].copy(),
                                           settings['profiles'][self.profile].copy())
            self.index_viewer.update_settings(profile_settings)
            self.story_viewer.set_hotkeys(profile_settings['hotkeys'])
        if style != self.style:
            self.style = copy.deepcopy(style)
            self.update_style(style)


    def update_style(self, style):
        try:
            css = self.css_template.format(**style)
            indexcss = self.index_css_template.format(**style)
        except KeyError as e:
            print(e)
            self.terminal.error('Invalid style config: key missing')
            return
        self.setStyleSheet(css)
        self.index_viewer.css = indexcss
        self.index_viewer.refresh_view(keep_position=True)


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



def read_config():
    configpath = join(getenv('HOME'), '.config', 'sapfo')
    configfile = join(configpath, 'settings.json')
    stylefile = join(configpath, 'style.json')
    common.make_sure_config_exists(configfile, common.local_path('default_settings.json'))
    common.make_sure_config_exists(stylefile, common.local_path('defaultstyle.json'))
    return common.read_json(configfile), common.read_json(stylefile)


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

    class AppEventFilter(QtCore.QObject):
        activation_event = QtCore.pyqtSignal()
        def eventFilter(self, object, event):
            if event.type() == QtCore.QEvent.ApplicationActivate:
                self.activation_event.emit()
            return False
    app.event_filter = AppEventFilter()
    app.installEventFilter(app.event_filter)

    window = MainWindow(args.profile, app.event_filter.activation_event)
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
