from datetime import datetime
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple, cast

from PyQt5.QtCore import QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from . import declin
from .declin import (ContainerSection, ItemSection, LineSection, Section,
                     StyleSpec)
from .declin.types import AttributeRef, Color, Direction, VerticalAlign


class Model(NamedTuple):
    main: str
    sections: Dict[str, Section]
    tag_colors: Dict[str, Color]


class StretchableRect(NamedTuple):
    x: int
    y: int
    width: Optional[int] = None
    height: Optional[int] = None

    def _with_offset(self, x: int = 0, y: int = 0) -> 'StretchableRect':
        if not x and not y:
            return self
        return StretchableRect(
            self.x + x, self.y + y,
            None if self.width is None else self.width - x,
            None if self.height is None else self.height - x)


class DrawGroup:
    def __init__(self, drawable: 'Drawable',
                 children: Optional[List['DrawGroup']] = None) -> None:
        self.drawable = drawable
        self.children = children or []

    def flatten(self) -> Iterable['Drawable']:
        yield self.drawable
        for child in self.children:
            yield from child.flatten()

    def size(self) -> QSize:
        return self.drawable.rect.size()

    def move(self, x: int = 0, y: int = 0) -> None:
        self.drawable.rect.translate(x, y)
        for child in self.children:
            child.move(x, y)

    def align_vertically(self, space: int) -> None:
        vertical_align = self.drawable.style.vertical_align
        height = self.drawable.rect.height()
        if space <= height:
            return
        mod_y = 0
        if vertical_align is VerticalAlign.MIDDLE:
            mod_y = (space - height) // 2
        elif vertical_align is VerticalAlign.BOTTOM:
            mod_y = space - height
        self.move(0, mod_y)


class Drawable:
    def __init__(self, rect: QRect, depth: int, style: StyleSpec
                 ) -> None:
        self.rect = rect
        # Lower depth means drawn after (on top of)
        self.depth = 0
        self.style = style

    def align_vertically(self, height: int) -> None:
        if height < self.rect.height():
            return
        mod_y = 0
        if self.style.vertical_align is VerticalAlign.MIDDLE:
            mod_y = (height - self.rect.height()) // 2
        elif self.style.vertical_align is VerticalAlign.BOTTOM:
            mod_y = height - self.rect.height()
        self.rect.translate(0, mod_y)

    def draw(self, painter: QPainter, y_offset: int = 0) -> None:
        s = self.style
        # Draw background
        background_color = get_color(s.background_color)
        bw = s.border.thickness
        r = QRectF(self.rect)\
            .translated(0, y_offset)\
            .adjusted(s.margin.left + bw / 2, s.margin.top + bw / 2,
                      -s.margin.right - bw / 2, -s.margin.bottom - bw / 2)
        if bw <= 0:
            pen = QPen(Qt.transparent)
        else:
            pen = QPen(get_color(s.border.color))
            pen.setWidth(s.border.thickness)
            pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(background_color)
        painter.drawRoundedRect(r, s.corner_radius, s.corner_radius)


class DrawableLine(Drawable):
    def draw(self, painter: QPainter, y_offset: int = 0) -> None:
        s = self.style
        rect = self.rect.adjusted(s.margin.left, s.margin.top,
                                  -s.margin.right, -s.margin.bottom)
        rect.translate(0, y_offset)
        # TODO: which color?
        painter.fillRect(rect, get_color(s.border.color))


class DrawableItem(Drawable):
    def __init__(self, text: str, rect: QRect, depth: int, style: StyleSpec
                 ) -> None:
        super().__init__(rect, depth, style)
        self.text = text

    def draw(self, painter: QPainter, y_offset: int = 0) -> None:
        super().draw(painter, y_offset)
        s = self.style
        painter.setPen(get_color(s.text_color))
        painter.setFont(get_font(s))
        text_rect = self.rect.adjusted(s.left_space, s.top_space,
                                       -s.right_space, -s.bottom_space)
        text_rect.translate(0, y_offset)
        painter.drawText(text_rect, Qt.TextWordWrap, self.text)


def get_font(style: declin.StyleSpec) -> QFont:
    font = QFont(style.font.family)
    font.setPixelSize(style.font.size)
    if style.font.bold:
        font.setBold(True)
    if style.font.italic:
        font.setItalic(True)
    return font


def get_color(raw_color: Color) -> QColor:
    return QColor(raw_color.red, raw_color.green, raw_color.blue,
                  raw_color.alpha)


def calc_size_container(input_value: Dict[str, Any], section: ContainerSection,
                        model: Model, rect: StretchableRect, depth: int,
                        ) -> DrawGroup:
    s = section.style
    data: Iterable[Tuple[Any, Section]]
    if isinstance(section.source, list):
        data = ((input_value, model.sections[attr.name])
                for attr in section.source)
    elif isinstance(section.source, tuple):
        attr, delegate_ref = section.source
        delegate = model.sections[delegate_ref.name]
        # TODO: maybe not do a hack like this
        if section.name == 'tags':
            data = ((v, delegate) for v in sorted(input_value[attr.name]))
        else:
            data = ((v, delegate) for v in input_value[attr.name])
    left = s.left_space
    top = s.top_space
    hspace = s.horizontal_space
    vspace = s.vertical_space
    inner_rect = StretchableRect(
        rect.x + left,
        rect.y + top,
        rect.width - hspace if rect.width is not None else None,
        rect.height - vspace if rect.height is not None else None)
    children = []
    x_offset = 0
    y_offset = 0
    max_width = 0
    max_height = 0
    if section.direction is Direction.HORIZONTAL:
        row_items: List[DrawGroup] = []
        for value, child in data:
            child_group = calc_size(value, child, model,
                                    inner_rect._with_offset(x=x_offset, y=y_offset),
                                    depth-1)
            child_size = child_group.drawable.rect
            if inner_rect.width is not None \
                    and x_offset + child_size.width() > inner_rect.width:
                # New row, align all the previous items
                for item in row_items:
                    item.align_vertically(max_height)
                # Move down one row
                x_offset = 0
                y_offset += max_height + section.spacing
                max_height = 0
                row_items = []
                child_group = calc_size(value, child, model,
                                        inner_rect._with_offset(x=x_offset,
                                                                y=y_offset),
                                        depth-1)
                child_size = child_group.drawable.rect
            children.append(child_group)
            row_items.append(child_group)
            max_height = max(max_height, child_size.height())
            x_offset += child_size.width() + section.spacing
        # Align the last row if we have any items here
        for item in row_items:
            item.align_vertically(max_height)
    elif section.direction is Direction.VERTICAL:
        for value, child in data:
            child_group = calc_size(value, child, model,
                                    inner_rect._with_offset(x=x_offset, y=y_offset),
                                    depth-1)
            child_size = child_group.drawable.rect
            if inner_rect.height is not None \
                    and y_offset + child_size.height() > inner_rect.height:
                # Move right one column
                x_offset += max_width + section.spacing
                y_offset = 0
                max_width = 0
                child_group = calc_size(value, child, model,
                                        inner_rect._with_offset(x=x_offset,
                                                                y=y_offset),
                                        depth-1)
                child_size = child_group.drawable.rect
            children.append(child_group)
            max_width = max(max_width, child_size.width())
            y_offset += child_size.height() + section.spacing
    if children:
        total_width = (max(c.drawable.rect.x() + c.drawable.rect.width()
                           for c in children) - inner_rect.x + hspace)
        total_height = (max(c.drawable.rect.y() + c.drawable.rect.height()
                            for c in children) - inner_rect.y + vspace)
    else:
        total_width = 0
        total_height = 0
    out_rect = QRect(rect.x, rect.y, total_width, total_height)
    return DrawGroup(Drawable(out_rect, depth, s), children=children)


def calc_size_item(input_value: Any, section: ItemSection,
                   model: Model, rect: StretchableRect, depth: int,
                   ) -> DrawGroup:
    data = [(input_value.get(x.name, None) if x.name else input_value)
            if isinstance(x, AttributeRef) else x
            for x in section.data]
    if section.when_empty and not any(x for x in data):
        return calc_size(input_value, model.sections[section.when_empty.name],
                         model, rect, depth)
    s = section.style
    # Special hack for tag colors
    if section.name == 'tag' and len(data) == 1 \
            and data[0] in model.tag_colors:
        s = s.replace(background_color=model.tag_colors[cast(str, data[0])])
    # Some special formatting
    for n in range(len(data)):
        if data[n] is None:
            data[n] = ''
        elif isinstance(data[n], datetime):
            data[n] = data[n].strftime(section.date_fmt)
        elif isinstance(data[n], float) and section.date_fmt:
            data[n] = datetime.fromtimestamp(data[n]).strftime(
                section.date_fmt)
    text = section.fmt.format(*data).replace('\\n', '\n')
    if not text:
        return DrawGroup(Drawable(QRect(rect.x, rect.y, 0, 0), depth, s))
    font_metrics = QFontMetrics(get_font(s))
    if rect.width is None:
        max_width = 10000
    else:
        max_width = rect.width - s.horizontal_space
    if rect.height is None:
        max_height = 10000
    else:
        max_height = rect.height - s.vertical_space
    bounding_rect = QRect(rect.x + s.left_space,
                          rect.y + s.top_space,
                          max_width, max_height)
    wrap = Qt.TextWordWrap if s.wrap else 0
    text_rect = font_metrics.boundingRect(bounding_rect, wrap, text)
    full_rect = text_rect.adjusted(-s.left_space, -s.top_space,
                                   s.right_space, s.bottom_space)
    return DrawGroup(DrawableItem(text, full_rect, depth, s))


def calc_size_line(section: LineSection, rect: StretchableRect,
                   depth: int) -> DrawGroup:
    s = section.style
    if section.thickness <= 0:
        return DrawGroup(Drawable(QRect(rect.x, rect.y, 0, 0), depth, s))
    if section.direction is Direction.HORIZONTAL:
        if rect.width is None:
            raise ValueError('max_width cannot be uncapped '
                             'for a horizontal line')
        size = QRect(rect.x, rect.y, rect.width,
                     (s.margin.top + s.margin.bottom + section.thickness))
    elif section.direction is Direction.VERTICAL:
        if rect.height is None:
            raise ValueError('max_height cannot be uncapped '
                             'for a vertical line')
        size = QRect(rect.x, rect.y,
                     (s.margin.left + s.margin.right + section.thickness),
                     rect.height)
    return DrawGroup(DrawableLine(size, depth, s))


def calc_size(input_value: Dict[str, Any], section: Section, model: Model,
              rect: StretchableRect, depth: int) -> DrawGroup:
    if isinstance(section, ContainerSection):
        return calc_size_container(input_value, section, model,
                                   rect, depth)
    elif isinstance(section, ItemSection):
        return calc_size_item(input_value, section, model,
                              rect, depth)
    elif isinstance(section, LineSection):
        return calc_size_line(section, rect, depth)
    else:
        raise NotImplementedError(str(type(section)))
