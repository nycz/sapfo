#!/usr/bin/env python3
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from libsyntyche.cli import ArgumentRules, Command
from libsyntyche.widgets import Signal0, mk_signal0
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from .backstorywindow import BackstoryWindow
from .common import (CSS_FILE, DATA_DIR, DECLIN_FILE, Settings,
                     read_with_default)
from .indexview import IndexView
from .taggedlist import ATTR_FILE, Entry


class MainWindow(QtWidgets.QWidget):
    def __init__(self, configdir: Optional[Path],
                 activation_event: Signal0, dry_run: bool) -> None:
        super().__init__()
        if configdir:
            self.configdir = configdir
        else:
            self.configdir = Path.home() / '.config' / 'sapfo'
        # Load settings
        self.css = (DATA_DIR / CSS_FILE).read_text(encoding='utf-8')
        self.declin = (DATA_DIR / DECLIN_FILE).read_text(encoding='utf-8')
        self.css_override = read_with_default(self.configdir / CSS_FILE)
        self.declin_override = read_with_default(self.configdir / DECLIN_FILE)
        self.setStyleSheet(self.css + '\n' + self.css_override)
        self.settings, missing_keys = Settings.load(self.configdir)
        self.setWindowTitle(self.settings.title)
        activation_event.connect(self.reload_settings)
        self.force_quit_flag = False

        # Create layouts
        self.stack = QtWidgets.QStackedLayout(self)

        # Index viewer
        self.index_view = IndexView(self, dry_run,
                                    self.settings,
                                    self.configdir / 'state',
                                    self.configdir / 'terminal_history',
                                    self.declin, self.declin_override)
        self.stack.addWidget(self.index_view)
        if missing_keys:
            keys = ', '.join(f'"{k}"' for k in missing_keys)
            self.index_view.terminal.error(f'Some keys are missing from your '
                                           f'config: {keys}')

        # Backstory editor
        self.backstory_termhistory_path = self.configdir / 'backstory_history'
        if not self.backstory_termhistory_path.exists():
            self.backstory_termhistory_path.mkdir(mode=0o755, parents=True)
        self.backstorywindows: Dict[Path, BackstoryWindow] = {}

        # Misc
        self.connect_signals()
        self.show()
        self.index_view.reload_view()

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
        self.index_view.view_meta.connect(self.open_backstory_editor)
        self.settings.title_changed.connect(self.setWindowTitle)
        self.index_view.terminal.add_command(Command(
            'quit', 'Quit sapfo',
            self.close,
            short_name='q',
            args=ArgumentRules.NONE
        ))

    def show_index(self) -> None:
        self.stack.setCurrentWidget(self.index_view)
        self.index_view.terminal.setFocus()

    def open_backstory_editor(self, entry: Entry) -> None:
        if entry[ATTR_FILE] in self.backstorywindows:
            self.backstorywindows[entry[ATTR_FILE]].activateWindow()
            self.backstorywindows[entry[ATTR_FILE]].raise_()
            return
        bsw = BackstoryWindow(entry, self.settings,
                              self.backstory_termhistory_path)
        bsw.setStyleSheet(self.styleSheet())
        self.backstorywindows[entry[ATTR_FILE]] = bsw
        bsw.closed.connect(self.forget_backstory_window)

    def forget_backstory_window(self, file: Path) -> None:
        bsw = self.backstorywindows[file]
        bsw.deleteLater()
        del self.backstorywindows[file]

    def reload_settings(self) -> None:
        self.settings.reload(self.configdir)
        css_override = read_with_default(self.configdir / CSS_FILE)
        if self.css_override != css_override:
            self.css_override = css_override
            css = self.css + '\n' + self.css_override
            self.setStyleSheet(css)
            self.index_view.setStyleSheet(css)
            for bsw in self.backstorywindows.values():
                bsw.setStyleSheet(css)
        declin_override = read_with_default(self.configdir / DECLIN_FILE)
        if self.declin_override != declin_override:
            self.declin_override = declin_override
            self.index_view.entry_view.update_gui(self.declin_override)

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


def main() -> int:
    import argparse
    from os.path import isdir
    parser = argparse.ArgumentParser()

    def valid_dir(dirname: str) -> Optional[str]:
        if isdir(dirname):
            return dirname
        parser.error(f'Directory does not exist: {dirname}')
    parser.add_argument('-c', '--config-directory', type=valid_dir)
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='don\'t write anything to disk')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)

    class AppEventFilter(QtCore.QObject):
        activation_event = mk_signal0()

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
