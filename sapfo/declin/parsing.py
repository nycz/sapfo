import enum
from itertools import chain
import re
from typing import (Any, cast, Dict, List, NamedTuple, Optional,
                    Set, Tuple, Union)

from .common import Constants, ParsingError, Pos, Token, TokenType
from .types import (AttributeRef, Border, Color, Direction,
                    Font, HorizontalAlign, ItemRef, Margins, VerticalAlign)


COMMENT_CHAR = ';'
SPECIAL_PREFIX = '!'
SECTION_RX = fr'{re.escape(SPECIAL_PREFIX)}?[A-Z][A-Z0-9_]*(?=$|\s)'
DEFAULT_CMD = f'{SPECIAL_PREFIX}DEFAULT'
EXPORT_CMD = f'{SPECIAL_PREFIX}EXPORT'


RawSection = List[Tuple[int, str]]


class Chunks(NamedTuple):
    default: RawSection
    export: RawSection
    sections: List[RawSection]


def text_to_chunks(code: str) -> Chunks:
    default: Optional[List[Tuple[int, str]]] = None
    export: Optional[List[Tuple[int, str]]] = None
    chunks: List[List[Tuple[int, str]]] = [[]]
    # Split into chunks
    for line_num, line_text in enumerate(chain(code.splitlines(), [None]), 1):
        # Check the specials
        if line_text and line_text.startswith(SPECIAL_PREFIX):
            cmd = line_text.split(None, 1)[0]
            if cmd not in (DEFAULT_CMD, EXPORT_CMD):
                raise ParsingError(f'unknown special section: {line_text!r}',
                                   Pos(line_text, line_num))
            elif cmd == DEFAULT_CMD and default is not None:
                raise ParsingError('multiple DEFAULT sections',
                                   Pos(line_text, line_num))
            elif cmd == EXPORT_CMD and export is not None:
                raise ParsingError('multiple EXPORT sections',
                                   Pos(line_text, line_num))
        # Found a chunk starting line
        latest_chunk = chunks[-1]
        if line_text is None or re.match(SECTION_RX, line_text):
            if latest_chunk:
                if latest_chunk[0][1].startswith(DEFAULT_CMD):
                    default = chunks.pop()
                elif latest_chunk[0][1].startswith(EXPORT_CMD):
                    export = chunks.pop()
                chunks.append([])
                latest_chunk = chunks[-1]
            if line_text is not None:
                latest_chunk.append((line_num, line_text))
        # Found an empty line or a full line comment
        elif not line_text.strip() \
                or line_text.lstrip().startswith(COMMENT_CHAR):
            pass
        # Found regular line
        elif re.match(r'\s', line_text):
            if latest_chunk:
                latest_chunk.append((line_num, line_text))
            else:
                raise ParsingError('code outside section',
                                   Pos(line_text, line_num))
        # Invalid chunk
        else:
            raise ParsingError('all code except section names '
                               'has to be indented', Pos(line_text, line_num))
    if default is None:
        raise ParsingError('missing DEFAULT section')
    if export is None:
        raise ParsingError('missing EXPORT section')
    return Chunks(default=default, export=export, sections=chunks)


def parse_value(text: str, row: int, col: int) -> Tuple[Token, str]:
    if not text.strip() or text.lstrip().startswith(COMMENT_CHAR):
        raise ParsingError('missing value')
    # String
    str_match = re.match(r'''("(?:[^"]|\\")*"|'(?:[^']|\\')*')''', text)
    if str_match:
        return Token(TokenType.STRING, str_match[0],
                     row, col, str_match[0][1:-1]), text[str_match.end():]
    # Number
    num_match = re.match(r'\d+\b', text)
    if num_match:
        return Token(TokenType.INT, num_match[0],
                     row, col, int(num_match[0])), text[num_match.end():]
    # Color
    color_match = re.match(r'#[0-9a-fA-F]+\b', text)
    if color_match:
        return Token(TokenType.COLOR, color_match[0],
                     row, col, color_match[0]), text[color_match.end():]
    # Attribute
    attr_match = re.match(r'([.][a-z][a-z0-9_]*\b|[.](?:\s|$))', text)
    if attr_match:
        return Token(TokenType.ATTRIBUTE, attr_match[0],
                     row, col, attr_match[0][1:]), text[attr_match.end():]
    # Names
    name_match = re.match(r'[a-z][a-z0-9_]*\b', text)
    if name_match:
        bools = {
            'true': True,
            'false': False,
        }
        constants = {
            'top': Constants.TOP,
            'left': Constants.LEFT,
            'right': Constants.RIGHT,
            'bottom': Constants.BOTTOM,
            'horizontal': Constants.HORIZONTAL,
            'vertical': Constants.VERTICAL,
            'bold': Constants.BOLD,
            'not_bold': Constants.NOT_BOLD,
            'italic': Constants.ITALIC,
            'not_italic': Constants.NOT_ITALIC,
            'middle': Constants.MIDDLE,
            'center': Constants.CENTER,
        }
        if name_match[0] in bools:
            return Token(TokenType.BOOL, name_match[0],
                         row, col, bools[name_match[0]]
                         ), text[name_match.end():]
        elif name_match[0] in constants:
            return Token(TokenType.CONSTANT, name_match[0],
                         row, col, constants[name_match[0]]
                         ), text[name_match.end():]
        else:
            return Token(TokenType.NAME, name_match[0], row, col,
                         name_match[0]), text[name_match.end():]
    # Didn't find anything
    raise ParsingError(f'unknown value type: {text!r}')


class Statement(NamedTuple):
    key: Token
    values: List[Token]


def parse_statements(lines: List[Tuple[int, str]]) -> List[Statement]:
    out = []
    seen: Set[str] = set()
    for line_num, line_text in lines:
        match = re.fullmatch(r'\s+(\S+)(?:\s+(.+?))\s*', line_text)
        if match is None:
            raise ParsingError(f'invalid line', Pos(line_text, line_num))
        cmd = match[1]
        if cmd in seen:
            raise ParsingError(f'duplicate key: {cmd}',
                               Pos(line_text, line_num))
        seen.add(cmd)
        arg_str = match[2]
        values: List[Token] = []
        col = match.start(2)
        while arg_str and not arg_str.startswith(COMMENT_CHAR):
            value, new_str = parse_value(arg_str, line_num, col)
            values.append(value)
            new_str = new_str.lstrip()
            col += len(arg_str) - len(new_str)
            arg_str = new_str
        out.append(Statement(Token(TokenType.NAME, cmd, line_num, 0, cmd),
                             values))
    return out


# Parsing helpers

def _require(args: List[Token],
             length: Optional[int] = None,
             allow_empty: bool = False,
             type_: Optional[TokenType] = None,
             types: Optional[Set[TokenType]] = None,
             unique_types: Optional[Set[TokenType]] = None,
             ) -> None:
    """
    Check the arguments and raise ParsingError if they don't match the format.

    length - check how many arguments are provided
    allow_empty - allow zero or more arguments instead of one or more
    type_ - all arguments has to this type
    types - all arguments has to have one of these types
    unique_types - for each type, there has to be one argument with that type

    You can use multiple arguments at once but not all make sense.
    """
    if length is not None and len(args) != length:
        raise ParsingError('invalid argument count')
    if type_ is not None and any(a.type_ != type_ for a in args):
        raise ParsingError(f'invalid argument type, expected {type_}')
    if types is not None and any(a.type_ not in types for a in args):
        raise ParsingError(f'invalid argument type, expected one of {types}')
    if unique_types is not None:
        if len(unique_types) != len(args):
            raise ParsingError('invalid argument count')
        missing_types = unique_types - {a.type_ for a in args}
        if missing_types:
            raise ParsingError(f'missing argument types {missing_types}')
    if not allow_empty and not args:
        raise ParsingError('arguments missing')


# Parse StyleSpec

class StyleSpec:
    # Color
    _text_color: Color
    _background_color: Color
    # Text
    _font: Font
    # Margin etc
    _margin: Margins
    _padding: Margins
    _border: Border
    # Misc
    _corner_radius: int
    _wrap: bool
    _vertical_align: VerticalAlign
    _horizontal_align: HorizontalAlign

    @property
    def text_color(self) -> Color:
        return self._text_color

    @property
    def background_color(self) -> Color:
        return self._background_color

    @property
    def font(self) -> Font:
        return self._font

    @property
    def margin(self) -> Margins:
        return self._margin

    @property
    def padding(self) -> Margins:
        return self._padding

    @property
    def border(self) -> Border:
        return self._border

    @property
    def corner_radius(self) -> int:
        return self._corner_radius

    @property
    def wrap(self) -> bool:
        return self._wrap

    @property
    def vertical_align(self) -> VerticalAlign:
        return self._vertical_align

    @property
    def horizontal_align(self) -> HorizontalAlign:
        return self._horizontal_align

    @property
    def left_space(self) -> int:
        return self.margin.left + self.border.thickness + self.padding.left

    @property
    def right_space(self) -> int:
        return self.margin.right + self.border.thickness + self.padding.right

    @property
    def top_space(self) -> int:
        return self.margin.top + self.border.thickness + self.padding.top

    @property
    def bottom_space(self) -> int:
        return self.margin.bottom + self.border.thickness + self.padding.bottom

    @property
    def horizontal_space(self) -> int:
        return self.left_space + self.right_space

    @property
    def vertical_space(self) -> int:
        return self.top_space + self.bottom_space

    def replace(self, **kwargs: Any) -> 'StyleSpec':
        style = StyleSpec()
        for var_name in style.__annotations__.keys():
            clean_var_name = var_name[1:]  # drop the _ prefix
            if clean_var_name in kwargs:
                setattr(style, var_name, kwargs[clean_var_name])
            else:
                setattr(style, var_name, getattr(self, var_name))
        return style

    @classmethod
    def load(cls, statements: List[Statement],
             default_style: Optional['StyleSpec'] = None
             ) -> Tuple['StyleSpec', List[Statement]]:
        style = StyleSpec()
        remaining: List[Statement] = []
        for stmt in statements:
            key = stmt.key.lexeme
            args = stmt.values
            try:
                if key == 'text_color':
                    _require(args, length=1, type_=TokenType.COLOR)
                    style._text_color = Color.parse(args[0].lexeme)
                elif key == 'background_color':
                    _require(args, length=1, type_=TokenType.COLOR)
                    style._background_color = Color.parse(args[0].lexeme)
                elif key == 'font':
                    default_font = default_style.font if default_style else None
                    style._font = Font.load(args, default_font)
                elif key == 'margin':
                    default_margin = (default_style.margin
                                      if default_style else None)
                    style._margin = Margins.load(args, default_margin)
                elif key == 'padding':
                    default_padding = (default_style.padding
                                       if default_style else None)
                    style._padding = Margins.load(args, default_padding)
                elif key == 'border':
                    default_border = (default_style.border
                                      if default_style else None)
                    style._border = Border.load(args, default_border)
                elif key == 'corner_radius':
                    _require(args, length=1, type_=TokenType.INT)
                    style._corner_radius = cast(int, args[0].literal)
                elif key == 'wrap':
                    _require(args, length=1, type_=TokenType.BOOL)
                    style._wrap = cast(bool, args[0].literal)
                elif key == 'vertical_align':
                    _require(args, length=1, type_=TokenType.CONSTANT)
                    style._vertical_align \
                        = VerticalAlign._load(cast(Constants, args[0].literal))
                elif key == 'horizontal_align':
                    _require(args, length=1, type_=TokenType.CONSTANT)
                    style._horizontal_align \
                        = HorizontalAlign._load(cast(Constants, args[0].literal))
                else:
                    remaining.append(stmt)
            except ParsingError as e:
                if not e.pos:
                    e.pos = Pos('', stmt.key.row)
                raise e
        missing_keys: List[str] = []
        for var in style.__annotations__.keys():
            if not hasattr(style, var):
                if default_style is not None:
                    setattr(style, var, getattr(default_style, var))
                else:
                    missing_keys.append(var)
        if missing_keys:
            raise ParsingError(f'missing style keys: {missing_keys}')
        return style, remaining


# Parse sections

class SectionType(enum.Enum):
    COLUMN = enum.auto()
    ITEM = enum.auto()
    LINE = enum.auto()
    ROW = enum.auto()


class Section:
    _style: StyleSpec

    def __init__(self, name: str, style: StyleSpec) -> None:
        self._name = name
        self._style = style

    @property
    def name(self) -> str:
        return self._name

    @property
    def style(self) -> StyleSpec:
        return self._style


class ItemSection(Section):
    _data: List[Union[AttributeRef, str]]
    _when_empty: Optional[ItemRef] = None
    _fmt: str = '{}'
    _date_fmt: str = ''

    def __init__(self, name: str, lines: RawSection,
                 default_style: StyleSpec) -> None:
        statements = parse_statements(lines)
        style, remaining_statements = StyleSpec.load(statements, default_style)
        super().__init__(name, style)
        for stmt in remaining_statements:
            key = stmt.key.lexeme
            args = stmt.values
            try:
                if key == 'fmt':
                    _require(args, length=1, type_=TokenType.STRING)
                    self._fmt = cast(str, args[0].literal)
                elif key == 'date_fmt':
                    _require(args, length=1, type_=TokenType.STRING)
                    self._date_fmt = cast(str, args[0].literal)
                elif key == 'data':
                    # TODO: accept literals
                    _require(args, types={TokenType.ATTRIBUTE,
                                          TokenType.STRING})
                    self._data = [AttributeRef(cast(str, a.literal))
                                  if a.type_ == TokenType.ATTRIBUTE
                                  else a.literal for a in args]
                elif key == 'when_empty':
                    _require(args, length=1, type_=TokenType.NAME)
                    self._when_empty = ItemRef(args[0].lexeme)
                else:
                    # TODO: better logging
                    print(f'unrecognized attribute: {key}')
            except ParsingError as e:
                if not e.pos:
                    e.pos = Pos('', stmt.key.row)
                raise e

    @property
    def data(self) -> List[Union[AttributeRef, str]]:
        return self._data

    @property
    def fmt(self) -> str:
        return self._fmt

    @property
    def date_fmt(self) -> str:
        return self._date_fmt

    @property
    def when_empty(self) -> Optional[ItemRef]:
        return self._when_empty


class ContainerSection(Section):
    _direction: Direction
    _source: Union[List[ItemRef], Tuple[AttributeRef, ItemRef]]
    _wrap: bool = True
    _spacing: int = 0

    def __init__(self, name: str, lines: RawSection, default_style: StyleSpec,
                 direction: Direction) -> None:
        statements = parse_statements(lines)
        style, remaining_statements = StyleSpec.load(statements, default_style)
        super().__init__(name, style)
        self._direction = direction
        items: Optional[List[ItemRef]] = None
        delegate: Optional[Tuple[AttributeRef, ItemRef]] = None
        for stmt in remaining_statements:
            key = stmt.key.lexeme
            args = stmt.values
            try:
                if key == 'delegate':
                    _require(args, unique_types={TokenType.ATTRIBUTE,
                                                 TokenType.NAME})
                    attr_ref: AttributeRef
                    item_ref: ItemRef
                    for a in args:
                        if a.type_ == TokenType.ATTRIBUTE:
                            attr_ref = AttributeRef(cast(str, a.literal))
                        elif a.type_ == TokenType.NAME:
                            item_ref = ItemRef(cast(str, a.literal))
                    delegate = (attr_ref, item_ref)
                elif key == 'items':
                    _require(args, type_=TokenType.NAME)
                    items = [ItemRef(cast(str, a.literal)) for a in args]
                elif key == 'wrap':
                    _require(args, length=1, type_=TokenType.BOOL)
                    self._wrap = cast(bool, args[0].literal)
                elif key == 'spacing':
                    _require(args, length=1, type_=TokenType.INT)
                    self._spacing = cast(int, args[0].literal)
                else:
                    # TODO: better logging
                    print(f'unrecognized attribute: {key}')
            except ParsingError as e:
                if not e.pos:
                    e.pos = Pos('', stmt.key.row)
                raise e
        if items is not None and delegate is not None:
            raise ParsingError("can't have both items and delegate in the "
                               "same section", Pos(lines[0][1], lines[0][0]))
        elif items is None and delegate is None:
            raise ParsingError('missing items or delegate field',
                               Pos(lines[0][1], lines[0][0]))
        elif delegate is not None:
            self._source = delegate
        elif items is not None:
            self._source = items

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def source(self) -> Union[List[ItemRef], Tuple[AttributeRef, ItemRef]]:
        return self._source

    @property
    def wrap(self) -> bool:
        return self._wrap

    @property
    def spacing(self) -> int:
        return self._spacing


class LineSection(Section):
    _direction: Direction
    _thickness: int = 1

    def __init__(self, name: str, lines: RawSection,
                 default_style: StyleSpec) -> None:
        statements = parse_statements(lines)
        style, remaining_statements = StyleSpec.load(statements, default_style)
        super().__init__(name, style)
        for stmt in remaining_statements:
            key = stmt.key.lexeme
            args = stmt.values
            try:
                if key == 'direction':
                    _require(args, length=1, type_=TokenType.CONSTANT)
                    if args[0].literal is Constants.HORIZONTAL:
                        self._direction = Direction.HORIZONTAL
                    elif args[0].literal is Constants.VERTICAL:
                        self._direction = Direction.VERTICAL
                    else:
                        raise ParsingError(f'invalid value for direction: '
                                           f'{args[0]!r}')
                elif key == 'thickness':
                    _require(args, length=1, type_=TokenType.INT)
                    self._thickness = cast(int, args[0].literal)
                else:
                    # TODO: better logging
                    print(f'unrecognized attribute: {key}')
            except ParsingError as e:
                if not e.pos:
                    e.pos = Pos('', stmt.key.row)
                raise e
        if not hasattr(self, '_direction'):
            raise ParsingError(f'missing attribute direction',
                               Pos(lines[0][1], lines[0][0]))

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def thickness(self) -> int:
        return self._thickness


def parse_section(raw_section: RawSection, default_style: StyleSpec
                  ) -> Tuple[str, Section]:
    start_row, cmd_line = raw_section[0]
    match = cmd_line.split()
    cmd_pos = Pos(cmd_line, start_row)
    if len(match) == 1:
        raise ParsingError('no name specified for item', cmd_pos)
    elif len(match) > 2:
        raise ParsingError('too many arguments', cmd_pos)
    type_name, name = match
    try:
        section_type = SectionType[type_name]
    except KeyError:
        raise ParsingError('unknown section type', cmd_pos)

    content = raw_section[1:]
    section: Section
    if section_type is SectionType.ITEM:
        section = ItemSection(name, content, default_style)
    elif section_type is SectionType.ROW:
        section = ContainerSection(name, content, default_style,
                                   Direction.HORIZONTAL)
    elif section_type is SectionType.COLUMN:
        section = ContainerSection(name, content, default_style,
                                   Direction.VERTICAL)
    elif section_type is SectionType.LINE:
        section = LineSection(name, content, default_style)
    return name, section


def parse_default(raw_section: RawSection) -> StyleSpec:
    statements = parse_statements(raw_section[1:])
    try:
        style, remaining_statements = StyleSpec.load(statements)
    except ParsingError as e:
        e.message = f'[In DEFAULT] {e.message}'
        raise e
    if remaining_statements:
        print('unrecognized attributes in default style:',
              remaining_statements)
    return style


def parse_export(raw_section: RawSection) -> str:
    statements = parse_statements(raw_section[1:])
    main: Optional[str] = None
    remaining_statements = []
    for stmt in statements:
        key = stmt.key.lexeme
        args = stmt.values
        if key == 'main':
            _require(args, length=1, type_=TokenType.NAME)
            main = args[0].lexeme
        else:
            remaining_statements.append(stmt)
    if main is None:
        raise ParsingError('missing main def')
    if remaining_statements:
        print('unrecognized attributes in EXPORT:', remaining_statements)
    return main
