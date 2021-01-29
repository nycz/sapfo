import enum
import re
from typing import Any, List, Optional, cast

from .common import Constants, ParsingError, Token, TokenType


class BaseType:
    pass


class Direction(enum.Enum):
    HORIZONTAL = enum.auto()
    VERTICAL = enum.auto()


class VerticalAlign(enum.Enum):
    TOP = enum.auto()
    MIDDLE = enum.auto()
    BOTTOM = enum.auto()

    @classmethod
    def _load(cls, constant: Constants) -> 'VerticalAlign':
        values = {
            Constants.TOP: VerticalAlign.TOP,
            Constants.MIDDLE: VerticalAlign.MIDDLE,
            Constants.BOTTOM: VerticalAlign.BOTTOM,
        }
        if constant not in values:
            raise ParsingError(f'argument {constant} does not match a '
                               f'vertical alignment')
        return values[constant]


class HorizontalAlign(enum.Enum):
    LEFT = enum.auto()
    CENTER = enum.auto()
    RIGHT = enum.auto()

    @classmethod
    def _load(cls, constant: Constants) -> 'HorizontalAlign':
        values = {
            Constants.LEFT: HorizontalAlign.LEFT,
            Constants.CENTER: HorizontalAlign.CENTER,
            Constants.RIGHT: HorizontalAlign.RIGHT,
        }
        if constant not in values:
            raise ParsingError(f'argument {constant} does not match a '
                               f'horizontal alignment')
        return values[constant]


class AttributeRef(BaseType):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self._name == other._name


class ItemRef(BaseType):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self._name == other._name


class Color(BaseType):
    def __init__(self, red: int, green: int, blue: int, alpha: int) -> None:
        self._red = red
        self._green = green
        self._blue = blue
        self._alpha = alpha

    @property
    def red(self) -> int:
        return self._red

    @property
    def green(self) -> int:
        return self._green

    @property
    def blue(self) -> int:
        return self._blue

    @property
    def alpha(self) -> int:
        return self._alpha

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) \
            and self._red == other._red \
            and self._green == other._green \
            and self._blue == other._blue \
            and self._alpha == other._alpha

    @classmethod
    def parse(cls, text: str) -> 'Color':
        rx = r'#[0-9a-fA-F]'
        if re.fullmatch(rx + '{6}', text):
            r = text[1:3]
            g = text[3:5]
            b = text[5:7]
            a = 'ff'
        elif re.fullmatch(rx + '{3}', text):
            r = text[1] * 2
            g = text[2] * 2
            b = text[3] * 2
            a = 'ff'
        elif re.fullmatch(rx + '{8}', text):
            r = text[1:3]
            g = text[3:5]
            b = text[5:7]
            a = text[7:9]
        elif re.fullmatch(rx + '{4}', text):
            r = text[1] * 2
            g = text[2] * 2
            b = text[3] * 2
            a = text[4] * 2
        else:
            raise ParsingError(f'invalid color string {text!r}')
        return Color(int(r, 16), int(g, 16), int(b, 16), int(a, 16))


class Border(BaseType):
    def __init__(self, thickness: int, color: Color) -> None:
        self._thickness = thickness
        self._color = color

    @property
    def thickness(self) -> int:
        return self._thickness

    @property
    def color(self) -> Color:
        return self._color

    @classmethod
    def load(cls, tokens: List[Token],
             default_border: Optional['Border'] = None) -> 'Border':
        thickness: Optional[int] = None
        color: Optional[Color] = None
        for token in tokens:
            if token.type_ == TokenType.INT:
                if thickness is not None:
                    raise ParsingError('multiple border thicknesses')
                thickness = cast(int, token.literal)
            elif token.type_ == TokenType.COLOR:
                if color is not None:
                    raise ParsingError('multiple border colors')
                color = Color.parse(token.lexeme)
            else:
                raise ParsingError(f'unknown border argument: {token!r}')
        if default_border is None:
            if thickness is None:
                raise ParsingError('missing border thickness')
            if color is None:
                raise ParsingError('missing border color')
            return Border(thickness, color)
        else:
            return Border(thickness or default_border.thickness,
                          color or default_border.color)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) \
            and self._thickness == other._thickness \
            and self._color == other._color


class Font(BaseType):
    def __init__(self, family: str, size: int, bold: bool, italic: bool
                 ) -> None:
        self._family = family
        self._size = size
        self._bold = bold
        self._italic = italic

    @property
    def family(self) -> str:
        return self._family

    @property
    def size(self) -> int:
        return self._size

    @property
    def bold(self) -> bool:
        return self._bold

    @property
    def italic(self) -> bool:
        return self._italic

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) \
            and self._family == other._family \
            and self._size == other._size \
            and self._bold == other._bold \
            and self._italic == other._italic

    @classmethod
    def load(cls, tokens: List[Token], default_font: Optional['Font'] = None
             ) -> 'Font':
        family: Optional[str] = None
        size: Optional[int] = None
        bold: Optional[bool] = None
        italic: Optional[bool] = None
        for token in tokens:
            if token.type_ == TokenType.STRING:
                if family is not None:
                    raise ParsingError('multiple font names')
                family = cast(str, token.literal)
            elif token.type_ == TokenType.INT:
                if size is not None:
                    raise ParsingError('multiple font sizes')
                size = cast(int, token.literal)
            elif token.type_ == TokenType.CONSTANT:
                if token.literal is Constants.BOLD:
                    bold = True
                elif token.literal is Constants.NOT_BOLD:
                    bold = False
                elif token.literal is Constants.ITALIC:
                    italic = True
                elif token.literal is Constants.NOT_ITALIC:
                    italic = False
                else:
                    raise ParsingError(f'unknown font format: '
                                       f'{token.literal!r}')
            else:
                raise ParsingError(f'unknown font argument: {token!r}')
        if default_font is None:
            if family is None:
                raise ParsingError('missing font name')
            if size is None:
                raise ParsingError('missing font size')
            if bold is None:
                bold = False
            if italic is None:
                italic = False
            return Font(family, size, bold, italic)
        else:
            return Font(family or default_font.family,
                        size or default_font.size,
                        bold if bold is not None else default_font.bold,
                        italic if italic is not None else default_font.italic)


class Margins(BaseType):
    def __init__(self, top: int, left: int, right: int, bottom: int
                 ) -> None:
        self._top = top
        self._left = left
        self._right = right
        self._bottom = bottom

    @property
    def top(self) -> int:
        return self._top

    @property
    def left(self) -> int:
        return self._left

    @property
    def right(self) -> int:
        return self._right

    @property
    def bottom(self) -> int:
        return self._bottom

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) \
            and self._top == other._top \
            and self._left == other._left \
            and self._right == other._right \
            and self._bottom == other._bottom

    @classmethod
    def load(cls, tokens: List[Token],
             default_margins: Optional['Margins'] = None) -> 'Margins':
        if len(tokens) == 1 and tokens[0].type_ == TokenType.INT:
            data = cast(int, tokens[0].literal)
            return Margins(data, data, data, data)
        else:
            if len(tokens) % 2 != 0:
                raise ParsingError('margin options should be declared '
                                   'in pairs')
            pairs = [tuple(tokens[n:n+2]) for n in range(0, len(tokens), 2)]
            top: Optional[int] = None
            bottom: Optional[int] = None
            left: Optional[int] = None
            right: Optional[int] = None
            for key_token, value_token in pairs:
                if not key_token.type_ == TokenType.CONSTANT:
                    raise ParsingError(f'key has to be a constant, '
                                       f'not {value_token.type_!r}')
                if not value_token.type_ == TokenType.INT:
                    raise ParsingError(f'value has to be an int, '
                                       f'not {value_token.type_!r}')
                value = cast(int, value_token.literal)
                if key_token.literal is Constants.TOP:
                    top = value
                elif key_token.literal is Constants.BOTTOM:
                    bottom = value
                elif key_token.literal is Constants.LEFT:
                    left = value
                elif key_token.literal is Constants.RIGHT:
                    right = value
                elif key_token.literal is Constants.HORIZONTAL:
                    left = right = value
                elif key_token.literal is Constants.VERTICAL:
                    top = bottom = value
                else:
                    raise ParsingError(f'invalid key type {key_token!r}')
            if default_margins:
                return Margins(top=default_margins.top if top is None else top,
                               bottom=(default_margins.bottom
                                       if bottom is None else bottom),
                               left=(default_margins.left
                                     if left is None else left),
                               right=(default_margins.right
                                      if right is None else right))
            else:
                if top is None or bottom is None \
                        or left is None or right is None:
                    raise ParsingError('incomplete margins spec')
                return Margins(top=top, bottom=bottom, left=left, right=right)
