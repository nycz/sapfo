from typing import FrozenSet, NamedTuple


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
