#!/usr/bin/env python3

import collections
import copy
from os import getenv
from os.path import exists, expanduser, isdir, join, split, splitext
import re
import sys

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from libsyntyche.common import read_json, read_file, write_json, kill_theming, local_path, set_hotkey, make_sure_config_exists
from libsyntyche.fileviewer import FileViewer
from terminal import Terminal
from indexframe import IndexFrame
from viewerframe import ViewerFrame
from metaframe import MetaFrame


class MainWindow(QtGui.QFrame):
    def __init__(self, configdir, activation_event, dry_run):
        super().__init__()
        self.setWindowTitle('Sapfo')
        self.configdir = configdir
        activation_event.connect(self.reload_settings)
        self.force_quit_flag = False

        # Create layouts
        self.stack = QtGui.QStackedLayout(self)
        kill_theming(self.stack)
        self.index_widget = QtGui.QWidget(self)
        layout = QtGui.QVBoxLayout(self.index_widget)
        kill_theming(layout)

        # Index viewer
        self.index_viewer = IndexFrame(self.index_widget, dry_run)
        layout.addWidget(self.index_viewer, stretch=1)

        # Terminal
        self.terminal = Terminal(self.index_widget, self.index_viewer.get_tags)
        layout.addWidget(self.terminal)

        # Add both to stack
        self.stack.addWidget(self.index_widget)

        # Story viewer
        self.story_viewer = ViewerFrame(self)
        self.stack.addWidget(self.story_viewer)

        # Meta viewer
        self.meta_viewer = MetaFrame(self)
        self.stack.addWidget(self.meta_viewer)

        # Popup viewer
        self.popup_viewer = FileViewer(self)
        self.stack.addWidget(self.popup_viewer)
        set_hotkey('Home', self.popup_viewer, self.show_index)

        # Load settings
        self.defaultstyle = read_json(local_path('defaultstyle.json'))
        self.css_template = read_file(local_path(join('templates','template.css')))
        self.index_css_template = read_file(local_path(join('templates','index_page.css')))
        self.viewer_css_template = read_file(local_path(join('templates','viewer_page.css')))
        self.settings, self.style = {}, {}
        self.reload_settings()

        # Misc
        self.connect_signals()
        self.show()

    def closeEvent(self, event):
        if self.stack.currentWidget() == self.meta_viewer:
            success = self.meta_viewer.save_tab()
            if success or self.force_quit_flag:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def quit(self, force):
        self.force_quit_flag = force
        self.close()

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
            (t.open_meta,               iv.open_meta),
            (t.new_entry,               self.new_entry),
            (t.zoom,                    iv.zoom),
            (self.story_viewer.show_index, self.show_index),
            (self.meta_viewer.show_index, self.show_index),
            (t.quit,                    self.close),
            (self.meta_viewer.quit,     self.quit),
            (iv.view_entry,             self.view_entry),
            (iv.view_meta,              self.view_meta),
            (iv.error,                  t.error),
            (iv.print_,                 t.print_),
            (iv.show_popup,             self.show_popup),
            (t.show_readme,             self.show_popup),
            (iv.set_terminal_text,      t.prompt)
        )
        for signal, slot in connects:
            signal.connect(slot)


    def new_entry(self, arg):
        def metadatafile(path):
            dirname, fname = split(path)
            return join(dirname, '.' + fname + '.metadata')
        file_exists = False
        tags = []
        new_entry_rx = re.match(r'\s*\(([^\(]*?)\)\s*(.+)\s*', arg)
        if not new_entry_rx:
            self.terminal.error('Invalid new entry command')
            return
        tagstr, path = new_entry_rx.groups()
        fullpath = expanduser(join(self.settings['path'], path))
        dirname, fname = split(fullpath)
        metadatafile = join(dirname, '.' + fname + '.metadata')
        if tagstr:
            tags = list({tag.strip() for tag in tagstr.split(',')})
        if exists(metadatafile):
            self.terminal.error('Metadata already exists for that file')
            return
        if exists(fullpath):
            file_exists = True
        # Fix the capitalization
        title = re.sub(r"[A-Za-z]+('[A-Za-z]+)?",
                       lambda mo: mo.group(0)[0].upper() + mo.group(0)[1:].lower(),
                       splitext(fname)[0].replace('-', ' '))
        try:
            open(fullpath, 'a').close()
            write_json(metadatafile, {'title': title, 'description': '', 'tags': tags})
        except Exception as e:
            self.terminal.error('Couldn\'t create the files: {}'.format(str(e)))
        else:
            self.index_viewer.reload_view()
            if file_exists:
                self.terminal.print_('New entry created, metadatafile added to existing file')
            else:
                self.terminal.print_('New entry created')


    def show_index(self):
        self.stack.setCurrentWidget(self.index_widget)
        self.terminal.setFocus()


    def view_entry(self, entry):
        self.story_viewer.view_page(entry)
        self.stack.setCurrentWidget(self.story_viewer)


    def view_meta(self, entry):
        self.meta_viewer.set_entry(entry)
        self.stack.setCurrentWidget(self.meta_viewer)

    def show_popup(self, *args):
        self.popup_viewer.set_page(*args)
        self.stack.setCurrentWidget(self.popup_viewer)


    def reload_settings(self):
        settings, style, stylepath = read_config(self.configdir, self.defaultstyle)
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
            self.meta_viewer.update_settings(settings)
            self.terminal.rootpath = settings['path']
            self.terminal.tagmacros = settings['tag macros']
            self.terminal.set_hotkeys(settings['hotkeys'])
        if style != self.style:
            self.style = style.copy()
            self.update_style(style)
            write_json(stylepath, style)


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
            return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if self.stack.currentWidget() == self.index_widget and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.keyReleaseEvent(ev)
        else:
            return super().keyReleaseEvent(ev)
    # =================================================


def read_config(configdir, defaultstyle):
    if configdir:
        configpath = configdir
    else:
        configpath = join(getenv('HOME'), '.config', 'sapfo')
    configfile = join(configpath, 'settings.json')
    stylefile = join(configpath, 'style.json')
    make_sure_config_exists(configfile, local_path('default_settings.json'))
    make_sure_config_exists(stylefile, local_path('defaultstyle.json'))
    # Make sure to update the style with the defaultstyle's values
    newstyle = read_json(stylefile)
    style = defaultstyle.copy()
    style.update({k:v for k,v in newstyle.items() if k in defaultstyle})
    return read_json(configfile), style, stylefile


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

    app = QtGui.QApplication(sys.argv)

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
