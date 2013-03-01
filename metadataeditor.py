from PyQt4 import QtCore, QtGui

from libsyntyche import common


class MetadataEditor(QtGui.QFrame):
    reload_index = QtCore.pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)

        self.path = ''
        self.metadata = {}

        layout = QtGui.QFormLayout(self)
        common.kill_theming(layout)

        class MetadataLabel(QtGui.QLabel): pass
        title_lbl = MetadataLabel('Title:')
        description_lbl = MetadataLabel('Description:')
        tags_lbl = MetadataLabel('Tags:')

        class MetadataInputField(QtGui.QLineEdit): pass
        self.title = MetadataInputField()
        self.description = MetadataInputField()
        self.tags = MetadataInputField()

        layout.addRow(title_lbl, self.title)
        layout.addRow(description_lbl, self.description)
        layout.addRow(tags_lbl, self.tags)

        self.title.returnPressed.connect(self.finished)
        self.description.returnPressed.connect(self.finished)
        self.tags.returnPressed.connect(self.finished)

        common.set_hotkey('Escape', self, self.hide)

        self.hide()

    def activate(self, path):
        self.path = path
        self.metadata = common.read_json(path)

        self.title.setText(self.metadata['title'])
        self.description.setText(self.metadata['description'])
        self.tags.setText(', '.join(self.metadata['tags']))

        self.setFocus()
        self.title.setFocus()
        self.show()


    def finished(self):
        self.metadata['title'] = self.title.text()
        self.metadata['description'] = self.description.text()
        if self.tags.text().strip():
            self.metadata['tags'] = self.tags.text().strip().split(', ')
        else:
            self.metadata['tags'] = []
        common.write_json(self.path, self.metadata)
        self.hide()
        self.reload_index.emit()

    def show(self):
        self.setDisabled(False)
        super().show()

    def hide(self):
        super().hide()
        self.setDisabled(True)
