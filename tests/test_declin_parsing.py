import pytest

from sapfo.declin.common import Token, TokenType
from sapfo.declin.parsing import parse_section, StyleSpec
from sapfo.declin.types import (AttributeRef, Border, Color, Direction, Font,
                                HorizontalAlign, Margins, VerticalAlign)


@pytest.fixture
def default_style():
    s = StyleSpec()
    s._text_color = Color(0, 0, 0, 255)
    s._background_color = Color(255, 255, 255, 255)
    s._font = Font('serif', 16, False, False)
    s._margin = Margins(0, 0, 0, 0)
    s._padding = Margins(0, 0, 0, 0)
    s._border = Border(0, Color(0, 0, 0, 255))
    s._corner_radius = 0
    s._wrap = False
    s._vertical_align = VerticalAlign.TOP
    s._horizontal_align = HorizontalAlign.LEFT
    return s


def test_parse_item_section(default_style):
    raw_section = [
        'ITEM foo',
        '    data .pos',
        '    margin top 2',
        '    text_color #123',
    ]
    name, section = parse_section(list(enumerate(raw_section)), default_style)
    assert name == 'foo'
    assert section.data == [AttributeRef('pos')]
    assert section.style.margin.top == 2
    assert section.style.margin.bottom == default_style.margin.bottom
    assert section.style.text_color == Color(0x11, 0x22, 0x33, 0xff)
    assert section.when_empty is None


def test_parse_line_section(default_style):
    raw_section = [
        'LINE foo',
        '    direction horizontal',
        '    margin 19',
        '    thickness 4',
    ]
    name, section = parse_section(list(enumerate(raw_section)), default_style)
    assert name == 'foo'
    assert section.direction == Direction.HORIZONTAL
    assert section.thickness == 4
    assert section.style.margin.top == 19
    assert section.style.margin.bottom == 19
    assert section.style.margin.left == 19
    assert section.style.margin.right == 19


# Low level stuff

@pytest.mark.parametrize(
    'text,color',
    [('#123', Color(0x11, 0x22, 0x33, 0xff)),
     ('#ff0099', Color(0xff, 0, 0x99, 0xff)),
     ('#98c61a', Color(0x98, 0xc6, 0x1a, 0xff)),
     ('#1234', Color(0x11, 0x22, 0x33, 0x44)),
     ('#98cf9b10', Color(0x98, 0xcf, 0x9b, 0x10))])
def test_parse_color(text, color):
    assert Color.parse(text) == color


def test_parse_border():
    border = Border.load([Token(TokenType.INT, '4', 0, 0, 4),
                          Token(TokenType.COLOR, '#abc', 0, 0, '#abc')])
    assert border == Border(4, Color(0xaa, 0xbb, 0xcc, 0xff))
