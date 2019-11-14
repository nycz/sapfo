import enum
from pathlib import Path
import re
from typing import (Any, Dict, List, NamedTuple, Optional,
                    Tuple, Type, Union)


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


class Color(NamedTuple):
    red: int
    green: int
    blue: int
    alpha: int

    @classmethod
    def _parse(cls, text: str) -> 'Color':
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


class Font(NamedTuple):
    family: str
    size: int
    bold: bool
    italic: bool

    @classmethod
    def _load(cls, items: Any, default_font: Optional['Font'] = None
              ) -> 'Font':
        family: Optional[str] = None
        size: Optional[int] = None
        bold: Optional[bool] = None
        italic: Optional[bool] = None
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if isinstance(item, str):
                if family is not None:
                    raise ParsingError('multiple font names')
                family = item
            elif isinstance(item, int):
                if size is not None:
                    raise ParsingError('multiple font sizes')
                size = item
            elif item is Constants.BOLD:
                bold = True
            elif item is Constants.NOT_BOLD:
                bold = False
            elif item is Constants.ITALIC:
                italic = True
            elif item is Constants.NOT_ITALIC:
                italic = False
            else:
                raise ParsingError(f'unknown font argument: {item!r}')
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


class Direction(enum.Enum):
    HORIZONTAL = enum.auto()
    VERTICAL = enum.auto()


class AttributeRef(NamedTuple):
    name: str


class ItemRef(NamedTuple):
    name: str


class SourceSpec(NamedTuple):
    data: Optional[List[str]] = None
    items: Optional[List[str]] = None


class Margins(NamedTuple):
    top: int = 0
    left: int = 0
    right: int = 0
    bottom: int = 0

    @classmethod
    def _load(cls, data: Any) -> 'Margins':
        if isinstance(data, int):
            return Margins(data, data, data, data)
        elif isinstance(data, list):
            if len(data) % 2 != 0:
                raise ParsingError('margin options should be declared '
                                   'in pairs')
            pairs = [tuple(data[n:n+2]) for n in range(0, len(data), 2)]
            out = {}
            for key, value in pairs:
                if not isinstance(value, int):
                    raise ParsingError(f'value has to be an int, '
                                       f'not {value!r}')
                if key is Constants.TOP:
                    out['top'] = value
                elif key is Constants.BOTTOM:
                    out['bottom'] = value
                elif key is Constants.LEFT:
                    out['left'] = value
                elif key is Constants.RIGHT:
                    out['right'] = value
                elif key is Constants.HORIZONTAL:
                    out['left'] = value
                    out['right'] = value
                elif key is Constants.VERTICAL:
                    out['top'] = value
                    out['bottom'] = value
                else:
                    raise ParsingError('invalid key type {key!r}')
            return Margins(**out)
        else:
            raise ParsingError('invalid margins spec')


def type_check_namedtuple(types: Dict[str, Type[Any]],
                          attrs: Dict[str, Any]) -> Dict[str, Type[Any]]:
    keep_attrs = {}
    for key, type_ in types.items():
        if key not in attrs:
            continue
        value = attrs[key]
        if type_ == Margins:
            value = Margins._load(value)
        elif not isinstance(value, type_):
            raise ParsingError(f'invalid type for {key}: '
                               f'{type(value)}')
        keep_attrs[key] = value
        del attrs[key]
    return keep_attrs


class StyleSpec(NamedTuple):
    # Color
    text_color: Color
    background_color: Color
    # Text
    font: Font
    # Margin etc
    margin: Margins
    padding: Margins
    border_width: Margins

    def _horizontal_space(self) -> int:
        width = 0
        if self.margin:
            width += self.margin.right + self.margin.left
        if self.padding:
            width += self.padding.right + self.padding.left
        if self.border_width:
            width += self.border_width.right + self.border_width.left
        return width

    def _vertical_space(self) -> int:
        height = 0
        if self.margin:
            height += self.margin.top + self.margin.bottom
        if self.padding:
            height += self.padding.top + self.padding.bottom
        if self.border_width:
            height += self.border_width.top + self.border_width.bottom
        return height

    @classmethod
    def _load(cls, attrs: Dict[str, Any],
              default_style: Optional['StyleSpec'] = None) -> 'StyleSpec':
        style_attrs = {}
        target_keys = set(cls._field_types.keys())
        if default_style is None \
                and not target_keys.issubset(attrs.keys()):
            missing_keys = target_keys - set(attrs.keys())
            raise ParsingError(f'Missing style keys: {missing_keys}')
        for key, type_ in cls._field_types.items():
            if key not in attrs:
                continue
            value = attrs[key]
            if type_ == Margins:
                value = Margins._load(value)
            elif type_ == Font:
                default_font = default_style.font if default_style else None
                value = Font._load(value, default_font)
            elif not isinstance(value, type_):
                raise ParsingError(f'invalid type for {key}: '
                                   f'{type(value)}')
            style_attrs[key] = value
            del attrs[key]
        if default_style:
            return default_style._replace(**style_attrs)
        else:
            return StyleSpec(**style_attrs)


class SectionType(enum.Enum):
    COLUMN = enum.auto()
    ITEM = enum.auto()
    LINE = enum.auto()
    ROW = enum.auto()


class ItemSection(NamedTuple):
    style: StyleSpec
    data: List[AttributeRef]
    fmt: str = '{}'
    date_fmt: str = ''

    @classmethod
    def _load(cls, style: StyleSpec, attrs: Dict[str, Any]) -> 'ItemSection':
        data = None
        if 'data' in attrs:
            data = attrs['data']
            del attrs['data']
            if not isinstance(data, list):
                data = [data]
            if not data or not all(isinstance(x, AttributeRef)
                                   for x in data):
                raise ParsingError('invalid data line')
        out = type_check_namedtuple({k: v for k, v in cls._field_types.items()
                                     if k not in {'style', 'data'}}, attrs)
        return ItemSection(style, data=data, **out)  # type: ignore


class ContainerSection(NamedTuple):
    style: StyleSpec
    direction: Direction
    source: Union[List[ItemRef], Tuple[AttributeRef, ItemRef]]
    wrap: bool = True
    spacing: int = 0

    @classmethod
    def _load(cls, style: StyleSpec, direction: Direction,
              attrs: Dict[str, Any]) -> 'ContainerSection':
        items = None
        if 'items' in attrs:
            items = attrs['items']
            del attrs['items']
            if not isinstance(items, list):
                items = [items]
            if not items or not all(isinstance(x, ItemRef)
                                    for x in items):
                raise ParsingError('invalid items line')
        delegate = None
        if 'delegate' in attrs:
            delegate = attrs['delegate']
            del attrs['delegate']
            try:
                assert isinstance(delegate, list)
                assert len(delegate) == 2
                assert isinstance(delegate[0], AttributeRef)
                assert isinstance(delegate[1], ItemRef)
            except AssertionError:
                raise ParsingError('invalid delegate line')
            else:
                delegate = tuple(delegate)
        if items is not None and delegate is not None:
            raise ParsingError("can't have both items and delegate in the "
                               "same section")
        source = items if items is not None else delegate

        ignore_keys = {'style', 'direction', 'source'}
        out = type_check_namedtuple({k: v for k, v in cls._field_types.items()
                                     if k not in ignore_keys}, attrs)
        return ContainerSection(style, direction, source,
                                **out)  # type: ignore


class LineSection(NamedTuple):
    style: StyleSpec
    direction: Direction
    thickness: int = 1

    @classmethod
    def _load(cls, style: StyleSpec, attrs: Dict[str, Any]) -> 'LineSection':
        ignore_keys = {'style', 'direction'}
        direction: Direction
        if 'direction' in attrs:
            raw_dir = attrs.pop('direction')
            if raw_dir == Constants.HORIZONTAL:
                direction = Direction.HORIZONTAL
            elif raw_dir == Constants.VERTICAL:
                direction = Direction.VERTICAL
            else:
                raise ParsingError(f'invalid value for direction: {raw_dir!r}')
        else:
            raise ParsingError('missing required attribute direction')
        out = type_check_namedtuple({k: v for k, v in cls._field_types.items()
                                     if k not in ignore_keys}, attrs)
        return LineSection(style, direction, **out)  # type: ignore


Section = Union[ItemSection, LineSection, ContainerSection]


# Syntax definitions

COMMENT_CHAR = ';'
SPECIAL_PREFIX = '!'
SECTION_RX = fr'{re.escape(SPECIAL_PREFIX)}?[A-Z][A-Z0-9_]*(?=$|\s)'


class Model(NamedTuple):
    main: str
    sections: Dict[str, Section]


def parse_value(text: str) -> Tuple[Any, str]:
    if not text.strip() or text.lstrip().startswith(COMMENT_CHAR):
        raise ParsingError('missing value')
    # String
    str_match = re.match(r'''("(?:[^"]|\\")*"|'(?:[^']|\\')*')''', text)
    if str_match:
        return str_match[0][1:-1], text[str_match.end():]
    # Number
    num_match = re.match(r'\d+\b', text)
    if num_match:
        return int(num_match[0]), text[num_match.end():]
    # Color
    color_match = re.match(r'#[0-9a-fA-F]+\b', text)
    if color_match:
        return Color._parse(color_match[0]), text[color_match.end():]
    # Attribute
    attr_match = re.match(r'([.][a-z][a-z0-9_]*\b|[.](?:\s|$))', text)
    if attr_match:
        return AttributeRef(attr_match[1][1:]), text[attr_match.end():]
    # Names
    name_match = re.match(r'[a-z][a-z0-9_]*\b', text)
    if name_match:
        constants = {
            'true': True,
            'false': False,
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
        }
        if name_match[0] in constants:
            return constants[name_match[0]], text[name_match.end():]
        else:
            return ItemRef(name_match[0]), text[name_match.end():]
    # Didn't find anything
    raise ParsingError(f'unknown value type: {text!r}')


def parse_statement(text: str) -> Tuple[str, List[Any]]:
    cmd, arg_str = text.lstrip().split(None, 1)
    values = []
    while arg_str and not arg_str.startswith(COMMENT_CHAR):
        value, new_str = parse_value(arg_str)
        values.append(value)
        arg_str = new_str.lstrip()
    return cmd, values


def parse_default(lines: List[Tuple[int, str]]) -> StyleSpec:
    attrs = get_attrs(lines)
    style = StyleSpec._load(attrs)
    if attrs:
        # TODO: better this
        print('Unrecognized attributes in DEFUALT:',
              set(attrs.keys()))
    return style


def parse_export(lines: List[Tuple[int, str]]) -> str:
    attrs = get_attrs(lines)
    if 'main' not in attrs:
        raise ParsingError('missing main def')
    main = attrs['main']
    if not isinstance(main, ItemRef):
        raise ParsingError(f'invalid main def: {main!r}')
    extra_keys = {k for k in attrs if k != 'main'}
    if extra_keys:
        print('Unrecognized attributes in EXPORT:', extra_keys)
    return main.name


def get_attrs(lines: List[Tuple[int, str]]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    for pos, line_text in lines:
        try:
            key, args = parse_statement(line_text)
        except ParsingError as e:
            e.pos = Pos(line_text, pos)
            raise e
        if key in attrs:
            raise ParsingError('duplicate key', Pos(line_text, pos))
        attrs[key] = None if not args else args[0] if len(args) == 1 else args
    return attrs


def parse_section(start_pos: int, cmd_line_text: str,
                  lines: List[Tuple[int, str]], default_style: StyleSpec
                  ) -> Tuple[str, Section]:
    match = cmd_line_text.split()
    cmd_pos = Pos(cmd_line_text, start_pos)
    if len(match) == 1:
        raise ParsingError('no name specified for item', cmd_pos)
    elif len(match) > 2:
        raise ParsingError('too many arguments', cmd_pos)
    type_name, name = match
    try:
        section_type = SectionType[type_name]
    except KeyError:
        raise ParsingError('unknown section type', cmd_pos)
    attrs = get_attrs(lines)
    style = StyleSpec._load(attrs, default_style)
    section: Section
    if section_type is SectionType.ITEM:
        section = ItemSection._load(style, attrs)
    elif section_type is SectionType.ROW:
        section = ContainerSection._load(style, Direction.HORIZONTAL, attrs)
    elif section_type is SectionType.COLUMN:
        section = ContainerSection._load(style, Direction.VERTICAL, attrs)
    elif section_type is SectionType.LINE:
        section = LineSection._load(style, attrs)
    if attrs:
        print('Unrecognized attributes in section:', list(attrs.keys()))
    return name, section


def parse(code: str) -> Model:
    chunks: List[List[Tuple[int, str]]] = [[]]
    # Split into chunks
    for line_num, line_text in enumerate(code.splitlines(), 1):
        latest_chunk = chunks[-1]
        # Found an empty line or a full line comment
        if not line_text.strip() \
                or line_text.lstrip().startswith(COMMENT_CHAR):
            pass
        # Found regular line
        elif re.match(r'\s', line_text):
            if latest_chunk:
                latest_chunk.append((line_num, line_text))
            else:
                raise ParsingError('code outside section',
                                   Pos(line_text, line_num))
        # Found a chunk starting line
        elif re.match(SECTION_RX, line_text):
            if latest_chunk:
                chunks.append([])
                latest_chunk = chunks[-1]
            latest_chunk.append((line_num, line_text))
        # Invalid chunk
        else:
            raise ParsingError('all code except section names '
                               'has to be indented', Pos(line_text, line_num))
    # The first chunk has to be DEFAULT
    first_chunk = chunks[0]
    first_pos, first_text = first_chunk[0]
    if first_text != f'{SPECIAL_PREFIX}DEFAULT':
        raise ParsingError('first section has to be DEFAULT',
                           Pos(first_text, first_pos))
    default_style = parse_default(first_chunk[1:])
    # Parse the chunks
    main_target: Optional[str] = None
    sections: Dict[str, Section] = {}
    for chunk in chunks[1:]:
        pos, cmd_line = chunk[0]
        if cmd_line.startswith(SPECIAL_PREFIX):
            cmd = cmd_line[1:]
            if cmd == 'EXPORT':
                main_target = parse_export(chunk[1:])
            else:
                raise ParsingError(f'unknown section type {cmd!r}',
                                   Pos(cmd_line, pos))
        else:
            name, section = parse_section(pos, cmd_line, chunk[1:],
                                          default_style)
            if name in sections:
                raise ParsingError(f'section name {name!r} already in use',
                                   Pos(cmd_line, pos))
            sections[name] = section
    if main_target is None:
        raise ParsingError('missing entry point')
    if not sections:
        raise ParsingError('no sections defined')
    return Model(main_target, sections)


if __name__ == '__main__':
    try:
        parse((Path(__file__).resolve().parent / 'data' / 'entry_layout.gui'
               ).read_text())
    except ParsingError as e:
        print(f'\x1b[1;31mError:\x1b[0m {e.message}')
        if e.pos:
            print(f'On line {e.pos.line_num}:   {e.pos.line_text}')
