from operator import itemgetter
from typing import Dict, List, Optional, Tuple, cast

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

from ..common import Settings
from ..declarative import fix_layout, label


class TagInfoList(QtWidgets.QScrollArea):
    error = pyqtSignal(str)
    print_ = pyqtSignal(str)

    class TagCountBar(QtWidgets.QWidget):
        def __init__(self, parent: QtWidgets.QWidget,
                     percentage: float) -> None:
            super().__init__(parent)
            self.percentage = percentage

        def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
            right_offset = (1 - self.percentage) * ev.rect().width()
            painter = QtGui.QPainter(self)
            painter.fillRect(ev.rect().adjusted(0, 0, -int(right_offset), 0),
                             painter.background())
            painter.end()

    def __init__(self, parent: QtWidgets.QWidget, settings: Settings) -> None:
        super().__init__(parent)
        self.setSizeAdjustPolicy(self.AdjustToContents)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.tag_colors: Dict[str, str] = settings.tag_colors
        settings.tag_colors_changed.connect(self.set_tag_colors)
        self.tag_macros: Dict[str, str] = settings.tag_macros
        settings.tag_macros_changed.connect(self.set_tag_macros)
        self.panel = QtWidgets.QWidget(self)
        self.panel.setObjectName('tag_info_list_panel')
        self.panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Maximum)
        layout = QtWidgets.QGridLayout(self.panel)
        layout.setColumnStretch(2, 1)
        layout.setHorizontalSpacing(10)
        # layout.setSizeConstraint(layout.SetMinAndMaxSize)
        # TODO: something less ugly than this
        self.setFixedHeight(200)
        self.panel.setLayout(layout)
        self.setWidget(self.panel)
        self.setWidgetResizable(True)
        self.hide()

    def clear(self) -> None:
        layout = self.panel.layout()
        while not layout.isEmpty():
            item = layout.takeAt(0)
            if item and item.widget() is not None:
                item.widget().deleteLater()

    def set_tag_colors(self, tag_colors: Dict[str, str]) -> None:
        self.tag_colors = tag_colors

    def set_tag_macros(self, tag_macros: Dict[str, str]) -> None:
        self.tag_macros = tag_macros

    def _make_tag(self, tag: str) -> QtWidgets.QWidget:
        tag_label_wrapper = QtWidgets.QWidget(self)
        tag_label = label(tag, 'tag', parent=tag_label_wrapper)
        if tag in self.tag_colors:
            tag_label.setStyleSheet(f'background: {self.tag_colors[tag]};')
        else:
            tag_label.setStyleSheet('background: #667;')
        sub_layout = QtWidgets.QHBoxLayout(tag_label_wrapper)
        fix_layout(sub_layout)
        sub_layout.addWidget(tag_label)
        sub_layout.addStretch()
        return tag_label_wrapper

    def view_tags(self, tags: List[Tuple[str, int]], sort_alphabetically: bool,
                  reverse: bool, name_filter: Optional[str]) -> None:
        self.clear()
        max_count = max(t[1] for t in tags)
        if sort_alphabetically:
            tags.sort(key=itemgetter(0))
        else:
            tags.sort(key=itemgetter(0), reverse=True)
            tags.sort(key=itemgetter(1))
        # If alphabetically, we want to default to ascending,
        # but if we're sorting by usage count, we want it descending.
        if reverse or (not sort_alphabetically and not reverse):
            tags.reverse()
        if name_filter:
            tags = [t for t in tags if name_filter in t[0]]
        layout = cast(QtWidgets.QGridLayout, self.panel.layout())
        for n, (tag, count) in enumerate(tags):
            # Tag name
            layout.addWidget(self._make_tag(tag), n, 0)
            # Tag count
            layout.addWidget(label(str(count), 'tag_info_count', parent=self),
                             n, 1, alignment=Qt.AlignBottom)
            # Tag bar
            count_bar = self.TagCountBar(self, count / max_count)
            layout.addWidget(count_bar, n, 2)
        self.show()

    def view_macros(self) -> None:
        # TODO: better view of this
        self.clear()
        layout = cast(QtWidgets.QGridLayout, self.panel.layout())
        for n, (tag, macro) in enumerate(sorted(self.tag_macros.items())):
            # Tag macro name
            layout.addWidget(self._make_tag('@' + tag), n, 0)
            # Tag macro expression
            layout.addWidget(label(macro, 'tag_info_macro_expression',
                                   parent=self, word_wrap=True), n, 1)
        self.show()
