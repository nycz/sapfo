from typing import cast, Dict, Iterable, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtWidgets import QLayout, QLayoutItem, QWidget

from .taggedlist import AttributeData, filter_entry


class ListLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None,
                 spacing: int = 0) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._items: List[QLayoutItem] = []
        self._spacing: int = spacing

    def sort(self, key: str, reverse: bool) -> None:
        self._items.sort(key=lambda x: getattr(x.widget().entry, key),  # type: ignore
                         reverse=reverse)
        for n, item in enumerate(self._items):
            w = item.widget()
            w.number = n  # type: ignore
            w.update_number()  # type: ignore
        self._do_layout(self.geometry())

    def filter_(self, filters: Iterable[Tuple[str, str]],
                attributedata: AttributeData,
                tagmacros: Dict[str, str]) -> None:
        n = 0
        for item in self._items:
            w = item.widget()
            if filter_entry(w.entry, filters, attributedata, tagmacros):  # type: ignore
                w.number = n  # type: ignore
                w.update_number()  # type: ignore
                w.show()
                n += 1
            else:
                w.hide()

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, spacing: int) -> None:
        self._spacing = spacing

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect)

    def heightForWidth(self, width: int) -> int:
        height = self._do_layout(QRect(0, 0, width, 0), dry_run=True)
        return height

    def hasHeightForWidth(self) -> bool:
        return True

    def expandingDirections(self) -> Qt.Orientations:
        return cast(Qt.Orientations, Qt.Vertical)

    def _do_layout(self, rect: QRect, dry_run: bool = False) -> int:
        x = rect.x()
        y = rect.y()
        width = rect.width()
        spacing = self._spacing
        n = 0
        for item in self._items:
            if item.widget().isHidden():
                continue
            if item.hasHeightForWidth():
                item_height = item.heightForWidth(width)
            else:
                item_height = item.sizeHint().height()
            if n > 0:
                y += spacing
            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y),
                                       QSize(width, item_height)))
            y += item_height
            n += 1
        return y - rect.y()

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
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

    def visibleItemAt(self, index: int) -> Optional[QLayoutItem]:
        try:
            return [x for x in self._items
                    if x.widget().isVisible()][index]
        except IndexError:
            return None

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def addLayout(self, layout: QLayout) -> None:
        self.addChildLayout(layout)
        self.addItem(layout)

    def count(self) -> int:
        return len(self._items)

    def visible_count(self) -> int:
        return len([x for x in self._items if x.widget().isVisible()])
