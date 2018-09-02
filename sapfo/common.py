from pathlib import Path
from typing import FrozenSet, NamedTuple


LOCAL_DIR = Path(__file__).resolve().parent


class ActiveFilters(NamedTuple):
    title: str
    description: str
    tags: FrozenSet[str]
    wordcount: int
    backstorywordcount: int
    backstorypages: int


class HtmlTemplates(NamedTuple):
    entry: str
    index_page: str
    tags: str


def local_path(path: str):
    return str(LOCAL_DIR / path)
