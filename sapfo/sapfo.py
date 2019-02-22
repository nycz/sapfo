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


CSS_FILE = 'qt.css'


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

        # Backstory editor
        self.backstory_termhistory_path = self.configdir / 'backstory_history'
        if not self.backstory_termhistory_path.exists():
            self.backstory_termhistory_path.mkdir(mode=0o755, parents=True)
        self.backstorywindows: Dict[Path, BackstoryWindow] = {}

        # Load settings
        self.css = (LOCAL_DIR / 'data' / CSS_FILE).read_text(encoding='utf-8')
        self.css_override = ''
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
            (self.index_view.quit,        self.close),
            (self.index_view.view_meta,   self.open_backstory_editor),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def show_index(self) -> None:
        self.stack.setCurrentWidget(self.index_view)
        self.index_view.terminal.setFocus()

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
        settings, css_override = read_config(self.configdir)
        # TODO: FIX THIS UGLY ASS SHIT
        # Something somewhere fucks up and changes the settings dict,
        # therefor the deepcopy(). Fix pls.
        if settings != self.settings:
            self.setWindowTitle(settings['title'] or 'Sapfo')
            self.settings = copy.deepcopy(settings)
            self.index_view.update_settings(settings)
            for bsw in self.backstorywindows.values():
                bsw.update_settings(settings)
        if self.css_override != css_override:
            self.css_override = css_override
            css = self.css + self.css_override
            self.setStyleSheet(css)
            for bsw in self.backstorywindows.values():
                bsw.setStyleSheet(css)

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


def read_config(configpath: Path) -> Tuple[Dict[str, Any], str]:
    try:
        style = (configpath / CSS_FILE).read_text(encoding='utf-8')
    except Exception:
        style = ''
    configfile = configpath / 'settings.json'
    if not configfile.exists():
        path = configfile.parent
        if not path.exists():
            path.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(LOCAL_DIR / 'data' / 'defaultconfig.json', configfile)
        print(f'No config found, copied the default to {configfile!r}.')
    return json.loads(configfile.read_text(encoding='utf-8')), style


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
