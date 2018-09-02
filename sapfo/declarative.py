from typing import Union, Mapping, Tuple, Iterable, Any

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QLayout

from .flowlayout import FlowLayout
__all__ = ['grid', 'hflow', 'hbox', 'vbox', 'label']


# TODO: enum and/or Qt.Orientation

# horizontal = 0
# vertical = 1

class GridPosition:
    def __getitem__(self, arg):
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

Item = QtWidgets.QLayoutItem

# LAYOUTS

StretchMap = Mapping[int, int]

PosOrRange = Union[int, Tuple[int, int]]

GridChildMap = Mapping[Tuple[PosOrRange, PosOrRange], Item]


def _fix_layout(layout):
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)


def _parse_span(val: PosOrRange) -> Tuple[int, int]:
    """Return position and column/row span."""
    if isinstance(val, tuple):
        return val[0], val[1] - val[0] + 1
    else:
        return val, 1


def _add_item(item, layout, *args):
    add = layout.addLayout if isinstance(item, QLayout) else layout.addWidget
    add(item, *args)


def grid(child_map: GridChildMap,
         col_stretch: StretchMap = None, row_stretch: StretchMap = None)\
        -> QtWidgets.QGridLayout:
    l = QtWidgets.QGridLayout()
    _fix_layout(l)
    if col_stretch:
        for pos, stretch in col_stretch.items():
            l.setColumnStretch(pos, stretch)
    if row_stretch:
        for pos, stretch in row_stretch.items():
            l.setRowStretch(pos, stretch)
    for (row, col), item in child_map.items():
        row, row_span = _parse_span(row)
        col, col_span = _parse_span(col)
        _add_item(item, l, row, col, row_span, col_span)
    return l


def box(*children: Iterable[Item], horizontal: bool = True):
    l = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight if horizontal
                             else QtWidgets.QBoxLayout.TopToBottom)
    _fix_layout(l)
    for item in children:
        _add_item(item, l)
    return l


def hbox(children: Iterable[Item]) -> QtWidgets.QHBoxLayout:
    return box(*children, horizontal=True)


def vbox(children: Iterable[Item]) -> QtWidgets.QVBoxLayout:
    return box(*children, horizontal=False)


def hflow(*children: Iterable[Item]) -> FlowLayout:
    l = FlowLayout()
    _fix_layout(l)
    for item in children:
        _add_item(item, l)
    return l

# def vflow(*children: Iterable[Item]) -> VFlowLayout:
#     pass


# WIDGETS

def label(data: Any, object_name: str, word_wrap: bool = False,
          parent = None) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(str(data), parent=parent)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(word_wrap)
    return lbl

# __all__ = [grid, label]
