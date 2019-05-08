from pathlib import Path
from typing import Optional, FrozenSet, NamedTuple


LOCAL_DIR = Path(__file__).resolve().parent

CACHE_DIR = Path.home() / '.cache' / 'sapfo'


class ActiveFilters(NamedTuple):
    title: Optional[str]
    description: Optional[str]
    recap: Optional[str]
    tags: Optional[FrozenSet[str]]
    wordcount: Optional[int]
    backstorywordcount: Optional[int]
    backstorypages: Optional[int]


def local_path(path: str) -> str:
    return str(LOCAL_DIR / path)
