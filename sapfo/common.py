import json
from pathlib import Path
import shutil
from typing import (Any, Dict, FrozenSet, List, NamedTuple, Optional,
                    Set, Tuple, Type, TypeVar, Union)

from PyQt5.QtCore import pyqtSignal, QObject


LOCAL_DIR = Path(__file__).resolve().parent
DATA_DIR = LOCAL_DIR / 'data'

CACHE_DIR = Path.home() / '.cache' / 'sapfo'

CSS_FILE = 'qt.css'
DECLIN_FILE = 'entry_layout.decl'


class ActiveFilters(NamedTuple):
    title: Optional[str]
    description: Optional[str]
    recap: Optional[str]
    tags: Optional[FrozenSet[str]]
    wordcount: Optional[int]
    backstorywordcount: Optional[int]
    backstorypages: Optional[int]


class SortBy(NamedTuple):
    key: str
    descending: bool

    def _order_name(self) -> str:
        return 'descending' if self.descending else 'ascending'


def local_path(path: str) -> str:
    return str(LOCAL_DIR / path)


T = TypeVar('T', bound='Settings')
U = TypeVar('U')


class Settings(QObject):
    filename = 'settings.json'
    default_config_path = DATA_DIR / 'defaultconfig.json'

    animate_terminal_output_changed = pyqtSignal(bool)
    backstory_default_pages_changed = pyqtSignal(dict)
    backstory_viewer_formats_changed = pyqtSignal(dict)
    capitalize_all_words_in_title_changed = pyqtSignal(bool)
    editor_changed = pyqtSignal(str)
    formatting_converters_changed = pyqtSignal(list)
    hotkeys_changed = pyqtSignal(dict)
    path_changed = pyqtSignal(Path)
    tag_colors_changed = pyqtSignal(dict)
    tag_macros_changed = pyqtSignal(dict)
    terminal_animation_interval_changed = pyqtSignal(int)
    title_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.animate_terminal_output = True
        self.backstory_viewer_formats: Dict[str, List[Union[str, int]]] = {}
        self.backstory_default_pages: Dict[str, str] = {}
        self.capitalize_all_words_in_title = True
        self.editor = ''
        self.formatting_converters: List[List[str]] = []
        self.hotkeys: Dict[str, str] = {}
        self.path = Path('/')
        self.tag_colors: Dict[str, str] = {}
        self.tag_macros: Dict[str, str] = {}
        self.terminal_animation_interval = 5
        self.title = ''

    @classmethod
    def _get_config_json(cls, config_path: Path) -> Dict[str, Any]:
        config_file = config_path / cls.filename
        if not config_file.exists():
            path = config_file.parent
            if not path.exists():
                path.mkdir(mode=0o755, parents=True, exist_ok=True)
            shutil.copyfile(cls.default_config_path, config_file)
            print(f'No config found, copied the default to {config_file!r}.')
        data: Dict[str, Any] = \
            json.loads(config_file.read_text(encoding='utf-8'))
        return data

    def _update_value(self, send_signals: bool, new_value: U,
                      old_value: U, changed_signal: pyqtSignal) -> U:
        if send_signals and new_value != old_value:
            changed_signal.emit(new_value)
        return new_value

    def reload(self, config_path: Path, send_signals: bool = True
               ) -> Set[str]:
        default_config = json.loads(self.default_config_path.read_text())
        config = self._get_config_json(config_path)
        missing_keys: Set[str] = set()

        def get(key: str) -> Any:
            if key in config:
                return config[key]
            else:
                missing_keys.add(key)
                return default_config[key]

        def u(new_value: U, old_value: U, changed_signal: pyqtSignal) -> U:
            return self._update_value(send_signals, new_value, old_value,
                                      changed_signal)

        # Animate terminal output
        self.animate_terminal_output = \
            u(get('animate terminal output'),
              self.animate_terminal_output,
              self.animate_terminal_output_changed)
        # Backstory viewer formats
        self.backstory_viewer_formats = \
            u(get('backstory viewer formats'),
              self.backstory_viewer_formats,
              self.backstory_viewer_formats_changed)
        # Backstory default pages
        self.backstory_default_pages = \
            u(get('backstory default pages'),
              self.backstory_default_pages,
              self.backstory_default_pages_changed)
        # Capitalize all words in the title when making a new entry
        self.capitalize_all_words_in_title = \
            u(get('capitalize all words in title'),
              self.capitalize_all_words_in_title,
              self.capitalize_all_words_in_title_changed)
        # Editor
        self.editor = u(get('editor'), self.editor, self.editor_changed)
        # Formatting converters
        self.formatting_converters = \
            u(get('formatting converters'),
              self.formatting_converters,
              self.formatting_converters_changed)
        # Hotkeys
        self.hotkeys = u(get('hotkeys'), self.hotkeys, self.hotkeys_changed)
        # Path
        self.path = u(Path(get('path')).expanduser(),
                      self.path, self.path_changed)
        # Tag colors
        self.tag_colors = \
            u(get('tag colors'), self.tag_colors, self.tag_colors_changed)
        # Tag macros
        self.tag_macros = \
            u(get('tag macros'), self.tag_macros, self.tag_macros_changed)
        # Terminal animation interval
        self.terminal_animation_interval = \
            u(get('terminal animation interval'),
              self.terminal_animation_interval,
              self.terminal_animation_interval_changed)
        # Title
        self.title = u(get('title'), self.title, self.title_changed)

        return missing_keys

    @classmethod
    def load(cls: Type[T], config_path: Path) -> Tuple[T, Set[str]]:
        # Create the settings object
        s = cls()
        missing_keys = s.reload(config_path, send_signals=False)
        return (s, missing_keys)


def read_with_default(path: Path, default: str = '') -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return default
