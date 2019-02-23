import enum
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal

from .common import LOCAL_DIR


CSS_FILE = 'qt.css'


class Key(enum.Enum):
    title = 'title'
    hotkeys = 'hotkeys'
    path = 'path'
    editor = 'editor'
    animate_terminal_output = 'animate terminal output'
    terminal_animation_interval = 'terminal animation interval'
    tag_colors = 'tag colors'
    tag_macros = 'tag macros'
    formatting_converters = 'formatting converters'
    chapter_strings = 'chapter strings'
    backstory_viewer_formats = 'backstory viewer formats'
    backstory_default_pages = 'backstory default pages'
    entry_length_template = 'entry length template'


T = TypeVar('T')


class Settings(QtCore.QObject):
    update_style = pyqtSignal(str)

    def __init__(self, config_dir: Optional[Path]) -> None:
        super().__init__()
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path.home() / '.config' / 'sapfo'

        self.css = (LOCAL_DIR / 'data' / CSS_FILE).read_text(encoding='utf-8')
        self.css_override = ''
        self._registered_callbacks: List[Callable] = []
        # Individual settings
        self.title = ''
        self.hotkeys: Dict[str, str] = {}
        self.path = ''
        self.editor = ''
        self.animate_terminal_output = False
        self.terminal_animation_interval = 10
        self.tag_colors: Dict[str, str] = {}
        self.tag_macros: Dict[str, str] = {}
        self.formatting_converters: List[List[str]] = []
        self.chapter_strings: List[List[str]] = []
        self.backstory_viewer_formats: Dict[str, List[str]] = {}
        self.backstory_default_pages: Dict[str, str] = {}
        self.entry_length_template = ''

    def register(self, callback: Callable) -> None:
        self._registered_callbacks.append(callback)

    def reload(self) -> None:
        settings, css_override = read_config(self.config_dir)
        updated_keys: Set[Key] = set()

        def update(key: Key, var: T) -> T:
            buf: T = settings[key.value]
            if buf != var:
                updated_keys.add(key)
            return buf
        # Read individual settings
        self.title = update(Key.title, self.title)
        self.hotkeys = update(Key.hotkeys, self.hotkeys)
        self.path = update(Key.path, self.path)
        self.editor = update(Key.editor, self.editor)
        self.animate_terminal_output = update(Key.animate_terminal_output,
                                              self.animate_terminal_output)
        self.terminal_animation_interval \
            = update(Key.terminal_animation_interval,
                     self.terminal_animation_interval)
        self.tag_colors = update(Key.tag_colors, self.tag_colors)
        self.tag_macros = update(Key.tag_macros, self.tag_macros)
        self.formatting_converters = update(Key.formatting_converters,
                                            self.formatting_converters)
        self.chapter_strings = update(Key.chapter_strings,
                                      self.chapter_strings)
        self.backstory_viewer_formats = update(Key.backstory_viewer_formats,
                                               self.backstory_viewer_formats)
        self.backstory_default_pages = update(Key.backstory_default_pages,
                                              self.backstory_default_pages)
        self.entry_length_template = update(Key.entry_length_template,
                                            self.entry_length_template)
        # Update settings
        if updated_keys:
            frozen_updated_keys = frozenset(updated_keys)
            for callback in self._registered_callbacks:
                callback(frozen_updated_keys)
        # Update css
        if self.css_override != css_override:
            self.css_override = css_override
            self.update_style.emit(self.css + self.css_override)


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
