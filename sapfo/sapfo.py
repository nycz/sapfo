#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt

from libsyntyche.common import make_sure_config_exists
from libsyntyche.fileviewer import FileViewer
from sapfo.indexframe import IndexFrame
from sapfo.viewerframe import ViewerFrame
from sapfo.backstorywindow import BackstoryWindow
from sapfo.taggedlist import Entry
from sapfo.common import LOCAL_DIR


class MainWindow(QtWidgets.QWidget):
    def __init__(self, configdir: Optional[Path],
                 activation_event: QtCore.pyqtSignal, dry_run: bool) -> None:
        super().__init__()
        self.setWindowTitle('Sapfo')
        if configdir:
            self.configdir = configdir
        else:
            self.configdir = Path.home() / '.config' / 'sapfo'
        activation_event.connect(self.reload_settings)
        self.force_quit_flag = False

        # Create layouts
        self.stack = QtWidgets.QStackedLayout(self)

        # Index viewer
        self.index_viewer = IndexFrame(self, dry_run,
                                       self.configdir / 'state')
        self.stack.addWidget(self.index_viewer)

        # Story viewer
        self.story_viewer = ViewerFrame(self)
        self.stack.addWidget(self.story_viewer)

        # Backstory editor
        self.backstorywindows: Dict[Path, BackstoryWindow] = {}

        # Popup viewer
        self.popup_viewer = FileViewer(self)
        self.stack.addWidget(self.popup_viewer)
        self.popuphomekey = QtWidgets.QShortcut(QtGui.QKeySequence(),
                                                self.popup_viewer,
                                                self.show_index)

        # Load settings
        self.css_parts = ['qt', 'index_page', 'viewer_page']
        self.css_overrides = {x: '' for x in self.css_parts}
        self.css = {x: (LOCAL_DIR / 'data' / 'templates' / f'{x}.css'
                        ).read_text(encoding='utf-8')
                    for x in self.css_parts}
        self.settings: Dict[str, Any] = {}
        self.reload_settings()

        # Misc
        self.connect_signals()
        self.show()

    def closeEvent(self, event: QtCore.QEvent) -> None:
        # Don't quit if any backstory windows are open
        if self.backstorywindows:
            self.index_viewer.terminal.error('One or more backstory windows '
                                             'are still open!')
            event.ignore()
        else:
            event.accept()

    def quit(self, force: bool) -> None:
        # This flag is not used atm
        self.force_quit_flag = force
        self.close()

    def connect_signals(self) -> None:
        connects = (
            (self.story_viewer.show_index,  self.show_index),
            (self.index_viewer.quit,        self.close),
            (self.index_viewer.view_entry,  self.view_entry),
            (self.index_viewer.view_meta,   self.open_backstory_editor),
            (self.index_viewer.show_popup,  self.show_popup),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def show_index(self) -> None:
        self.stack.setCurrentWidget(self.index_viewer)
        self.index_viewer.terminal.setFocus()

    def view_entry(self, entry: Entry) -> None:
        self.story_viewer.view_page(entry)
        self.stack.setCurrentWidget(self.story_viewer)

    def open_backstory_editor(self, entry: Entry) -> None:
        if entry.file in self.backstorywindows:
            self.backstorywindows[entry.file].activateWindow()
            self.backstorywindows[entry.file].raise_()
            return
        bsw = BackstoryWindow(entry, self.settings)
        bsw.setStyleSheet(self.styleSheet())
        self.backstorywindows[entry.file] = bsw
        bsw.closed.connect(self.forget_backstory_window)

    def forget_backstory_window(self, file: Path) -> None:
        bsw = self.backstorywindows[file]
        bsw.deleteLater()
        del self.backstorywindows[file]

    def show_popup(self, *args: Any) -> None:
        self.popup_viewer.set_page(*args)
        self.stack.setCurrentWidget(self.popup_viewer)

    def reload_settings(self) -> None:
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
            self.popuphomekey.setKey(QtGui.QKeySequence(
                    settings['hotkeys']['home']))
        # if self.css_overrides != css_overrides:
        self.update_style(css_overrides)

    def update_style(self, css_overrides: Dict[str, str]) -> None:
        css = self.css['qt'] + '\n' + css_overrides['qt']
        self.setStyleSheet(css)
        for bsw in self.backstorywindows.values():
            bsw.setStyleSheet(css)
        self.index_viewer.css = '\n'.join([self.css['index_page'],
                                           css_overrides['index_page']])
        self.story_viewer.css = '\n'.join([self.css['viewer_page'],
                                           css_overrides['viewer_page']])
        self.index_viewer.refresh_view(keep_position=True)
        if self.story_viewer.isEnabled():
            self.story_viewer.update_css()
        self.css_overrides = css_overrides

    # ===== Input overrides ===========================
    def keyPressEvent(self, ev: QtGui.QKeyEvent) -> Any:
        if self.stack.currentWidget() == self.index_viewer \
                and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.scroll_area.keyPressEvent(ev)
        else:
            return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev: QtGui.QKeyEvent) -> Any:
        if self.stack.currentWidget() == self.index_viewer \
                and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_viewer.scroll_area.keyReleaseEvent(ev)
        else:
            return super().keyReleaseEvent(ev)
    # =================================================


def read_config(configpath: Path, cssnames: Iterable[str]
                ) -> Tuple[Dict[str, Any], Dict[str, str]]:
    configfile = configpath / 'settings.json'
    styles = {}
    for name in cssnames:
        fullpath = configpath / f'{name}.css'
        try:
            data = fullpath.read_text(encoding='utf-8')
        except Exception:
            data = ''
        finally:
            styles[name] = data
    make_sure_config_exists(str(configfile),
                            str(LOCAL_DIR / 'data' / 'defaultconfig.json'))
    return json.loads(configfile.read_text(encoding='utf-8')), styles


def main() -> None:
    import argparse
    from os.path import isdir
    parser = argparse.ArgumentParser()

    def valid_dir(dirname: str) -> Optional[str]:
        if isdir(dirname):
            return dirname
        parser.error(f'Directory does not exist: {dirname}')
        return None
    parser.add_argument('-c', '--config-directory', type=valid_dir)
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='don\'t write anything to disk')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)

    class AppEventFilter(QtCore.QObject):
        activation_event = QtCore.pyqtSignal()

        def eventFilter(self, object: QtCore.QObject,
                        event: QtCore.QEvent) -> bool:
            if event.type() == QtCore.QEvent.ApplicationActivate:
                self.activation_event.emit()
            return False
    event_filter = AppEventFilter()
    app.installEventFilter(event_filter)
    config_dir = Path(args.config_directory) if args.config_directory else None

    window = MainWindow(config_dir,
                        event_filter.activation_event,
                        args.dry_run)
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
