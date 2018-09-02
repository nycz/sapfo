# Copyright (C) 2015 The Qt Company Ltd.
# Contact: http://www.qt.io/licensing/
#
# This file is part of the examples of the Qt Toolkit.
#
# You may use this file under the terms of the BSD license as follows:
#
# "Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#   * Neither the name of The Qt Company Ltd nor the names of its
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."

# Converted to python from:
# https://doc.qt.io/qt-4.8/qt-layouts-flowlayout-example.html


from typing import List, Optional

from PyQt5.QtCore import QPoint, QRect, QSize
from PyQt5.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0,
                 h_spacing: int = 0, v_spacing: int = 0) -> None:
        super().__init__(parent)
        self._margin = margin
        self.setContentsMargins(margin, margin, margin, margin)
        self._items: List[QLayoutItem] = []
        self._h_spacing: int = h_spacing
        self._v_spacing: int = v_spacing

    def spacing(self) -> int:
        return -1

    def setSpacing(self, spacing: int) -> None:
        self._h_spacing = spacing
        self._v_spacing = spacing

    def horizontalSpacing(self) -> int:
        return self._h_spacing

    def setHorizontalSpacing(self, spacing: int) -> None:
        self._h_spacing = spacing

    def verticalSpacing(self) -> int:
        return self._v_spacing

    def setVerticalSpacing(self, spacing: int) -> None:
        self._v_spacing = spacing

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect)

    def heightForWidth(self, width: int) -> int:
        height = self._do_layout(QRect(0, 0, width, 0), dry_run=True)
        return height

    def hasHeightForWidth(self) -> bool:
        return True

    # def expandingDirections(self):
        # it can never use more space than its size hint
        # return Qt.Horizontal

    def _do_layout(self, full_rect: QRect, dry_run: bool = False) -> int:
        left, top, right, bottom = self.getContentsMargins()
        rect = full_rect.adjusted(left, top, -right, -bottom)
        x = rect.x()
        y = rect.y()
        space_x = self._h_spacing
        space_y = self._v_spacing
        line_height = 0
        for item in self._items:
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + bottom

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2*self._margin, 2*self._margin)
        return size

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        try:
            return self._items[index]
        except IndexError:
            return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        try:
            return self._items.pop(index)
        except IndexError:
            return None

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def addLayout(self, layout: QLayout) -> None:
        self.addChildLayout(layout)
        self.addItem(layout)

    def count(self) -> int:
        return len(self._items)

