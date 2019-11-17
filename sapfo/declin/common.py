import enum
from typing import NamedTuple, Optional, Union


class Constants(enum.Enum):
    HORIZONTAL = enum.auto()
    VERTICAL = enum.auto()
    TOP = enum.auto()
    BOTTOM = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()
    BOLD = enum.auto()
    ITALIC = enum.auto()
    NOT_BOLD = enum.auto()
    NOT_ITALIC = enum.auto()
    CENTER = enum.auto()
    MIDDLE = enum.auto()


class TokenType(enum.Enum):
    ATTRIBUTE = enum.auto()
    BOOL = enum.auto()
    COLOR = enum.auto()
    CONSTANT = enum.auto()
    INT = enum.auto()
    NAME = enum.auto()
    SECTION_TYPE = enum.auto()
    STRING = enum.auto()


class Token(NamedTuple):
    type_: TokenType
    lexeme: str
    row: int
    col: int
    literal: Union[Constants, bool, str, int]


class Pos(NamedTuple):
    line_text: str
    line_num: int


class ParsingError(Exception):
    def __init__(self, message: str, pos: Optional[Pos] = None) -> None:
        self.message = message
        self.pos = pos

    def __str__(self) -> str:
        pos = f' on line {self.pos.line_num}' if self.pos else ''
        return f'Parsing error{pos}: {self.message}'
