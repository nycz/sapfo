#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt

from .backstorywindow import BackstoryWindow
from .common import LOCAL_DIR
from .indexview import IndexView
from .taggedlist import Entry
from .storyview import StoryView


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
        self.index_view = IndexView(self, dry_run,
                                    self.configdir / 'state',
                                    self.configdir / 'terminal_history')
        self.stack.addWidget(self.index_view)

        # Story viewer
        self.story_view = StoryView(self)
        self.stack.addWidget(self.story_view)

        # Backstory editor
        self.backstory_termhistory_path = self.configdir / 'backstory_history'
        if not self.backstory_termhistory_path.exists():
            self.backstory_termhistory_path.mkdir(mode=0o755, parents=True)
        self.backstorywindows: Dict[Path, BackstoryWindow] = {}

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
            self.index_view.terminal.error('One or more backstory windows '
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
            (self.story_view.show_index,  self.show_index),
            (self.index_view.quit,        self.close),
            (self.index_view.view_entry,  self.view_entry),
            (self.index_view.view_meta,   self.open_backstory_editor),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def show_index(self) -> None:
        self.stack.setCurrentWidget(self.index_view)
        self.index_view.terminal.setFocus()

    def view_entry(self, entry: Entry) -> None:
        self.story_view.view_page(entry)
        self.stack.setCurrentWidget(self.story_view)

    def open_backstory_editor(self, entry: Entry) -> None:
        if entry.file in self.backstorywindows:
            self.backstorywindows[entry.file].activateWindow()
            self.backstorywindows[entry.file].raise_()
            return
        bsw = BackstoryWindow(entry, self.settings,
                              self.backstory_termhistory_path)
        bsw.setStyleSheet(self.styleSheet())
        self.backstorywindows[entry.file] = bsw
        bsw.closed.connect(self.forget_backstory_window)

    def forget_backstory_window(self, file: Path) -> None:
        bsw = self.backstorywindows[file]
        bsw.deleteLater()
        del self.backstorywindows[file]

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
            self.index_view.update_settings(settings)
            self.story_view.update_settings(settings)
            for bsw in self.backstorywindows.values():
                bsw.update_settings(settings)
        if self.css_overrides != css_overrides:
            self.update_style(css_overrides)

    def update_style(self, css_overrides: Dict[str, str]) -> None:
        css = self.css['qt'] + '\n' + css_overrides['qt']
        self.setStyleSheet(css)
        for bsw in self.backstorywindows.values():
            bsw.setStyleSheet(css)
        self.index_view.css = '\n'.join([self.css['index_page'],
                                         css_overrides['index_page']])
        self.story_view.css = '\n'.join([self.css['viewer_page'],
                                         css_overrides['viewer_page']])
        self.index_view.refresh_view(keep_position=True)
        if self.story_view.isEnabled():
            self.story_view.update_css()
        self.css_overrides = css_overrides

    # ===== Input overrides ===========================
    def keyPressEvent(self, ev: QtGui.QKeyEvent) -> Any:
        if self.stack.currentWidget() == self.index_view \
                and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_view.on_external_key_event(ev, True)
        else:
            return super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev: QtGui.QKeyEvent) -> Any:
        if self.stack.currentWidget() == self.index_view \
                and ev.key() in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.index_view.on_external_key_event(ev, False)
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
    if not configfile.exists():
        path = configfile.parent
        if not path.exists():
            path.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(LOCAL_DIR / 'data' / 'defaultconfig.json', configfile)
        print(f'No config found, copied the default to {configfile!r}.')
    return json.loads(configfile.read_text(encoding='utf-8')), styles


def main() -> int:
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
