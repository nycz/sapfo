from typing import Any, Iterable, Mapping, Optional, Tuple, TypeVar, Union

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (QBoxLayout, QGridLayout, QHBoxLayout, QLayout,
                             QVBoxLayout, QWidget)

from .flowlayout import FlowLayout
__all__ = ['grid', 'hflow', 'hbox', 'vbox', 'label']


# TODO: enum and/or Qt.Orientation

# horizontal = 0
# vertical = 1

class GridPosition:
    def __getitem__(self, arg: Tuple[int, int]) -> Tuple[int, int]:
        raw_row, raw_col = arg
        row_span, col_span = 1, 1
        if isinstance(raw_row, slice):
            row = raw_row[0]
            row_span = raw_row.stop - raw_row.start + 1
        else:
            row = raw_row
        if isinstance(raw_col, slice):
            col = raw_col[0]
            col_span = raw_col.stop - raw_col.start + 1
        else:
            col = raw_col
        return ((row, row_span))


Item = Union[QWidget, QLayout]
Layout = Union[QBoxLayout, QGridLayout]


# LAYOUTS

StretchMap = Mapping[int, int]

PosOrRange = Union[int, Tuple[int, int]]

GridChildMap = Mapping[Tuple[PosOrRange, PosOrRange], Item]


def fix_layout(layout: QLayout) -> None:
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)


def _parse_span(val: PosOrRange) -> Tuple[int, int]:
    """Return position and column/row span."""
    if isinstance(val, tuple):
        return val[0], val[1] - val[0] + 1
    else:
        return val, 1


def _add_item(item: Union[QLayout, QWidget], layout: Union[Layout, FlowLayout],
              *args: Any) -> None:
    if isinstance(item, QLayout):
        if isinstance(layout, QGridLayout):
            layout.addLayout(item, *args)
        else:
            layout.addLayout(item)
    else:
        if isinstance(layout, QGridLayout):
            layout.addWidget(item, *args)
        else:
            layout.addWidget(item)


def grid(child_map: GridChildMap,
         col_stretch: Optional[StretchMap] = None,
         row_stretch: Optional[StretchMap] = None) -> QGridLayout:
    layout = QGridLayout()
    fix_layout(layout)
    if col_stretch:
        for pos, stretch in col_stretch.items():
            layout.setColumnStretch(pos, stretch)
    if row_stretch:
        for pos, stretch in row_stretch.items():
            layout.setRowStretch(pos, stretch)
    for (row, col), item in child_map.items():
        row, row_span = _parse_span(row)
        col, col_span = _parse_span(col)
        _add_item(item, layout, row, col, row_span, col_span)
    return layout


BoxT = TypeVar('BoxT', QHBoxLayout, QVBoxLayout)


def init_box_layout(children: Iterable[Item],
                    layout: BoxT) -> BoxT:
    fix_layout(layout)
    for item in children:
        _add_item(item, layout)
    return layout


def hbox(*children: Item) -> QtWidgets.QHBoxLayout:
    return init_box_layout(children, QHBoxLayout())


def vbox(*children: Item) -> QtWidgets.QVBoxLayout:
    return init_box_layout(children, QVBoxLayout())


def hflow(*children: Item) -> FlowLayout:
    layout = FlowLayout()
    fix_layout(layout)
    for item in children:
        _add_item(item, layout)
    return layout

# def vflow(*children: Iterable[Item]) -> VFlowLayout:
#     pass


# WIDGETS

def label(data: Any, object_name: str, word_wrap: bool = False,
          parent: Optional[QWidget] = None) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(str(data), parent=parent)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(word_wrap)
    return lbl

# __all__ = [grid, label]
