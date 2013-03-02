import os
import os.path
from os.path import join
import re

from PyQt4 import QtCore, QtGui, QtWebKit

from libsyntyche import common
import datalib
import infopanel
import metadataeditor


class ViewerFrame(QtGui.QFrame):

    class WebView(QtWebKit.QWebView):
        previous = QtCore.pyqtSignal()
        next = QtCore.pyqtSignal()
        wheel_event = QtCore.pyqtSignal(int)
        # Overrides
        def mouseReleaseEvent(self, ev):
            if ev.button() == QtCore.Qt.XButton1:
                self.previous.emit()
            elif ev.button() == QtCore.Qt.XButton2:
                self.next.emit()
            else:
                super().mouseReleaseEvent(ev)

        def wheelEvent(self, ev):
            viewport_size = self.page().viewportSize()
            true_size = self.page().currentFrame().contentsSize()
            # If there are scrollbars, do the regular thing
            if true_size.width() > viewport_size.width() \
                    or true_size.height() > viewport_size.height():
                super().wheelEvent(ev)
            else:
                self.wheel_event.emit(ev.delta())

    set_fullscreen = QtCore.pyqtSignal(bool)
    request_reload = QtCore.pyqtSignal()

    def __init__(self, title, data):
        super().__init__()
        self.title = title
        self.root_path = os.path.normpath(data['path'])
        self.generated_index_path = join(self.root_path,
                    'index_page_generated_{}.html'.format(title))
        # self.entry_pages = datalib.get_all_stories_with_pages(\
        #                     self.root_path, self.fname_rx, data['blacklist'])

        self.current_entry = []
        self.current_page = -1
        self.fullscreen = False

        # Layout
        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.webview = self.WebView(self)
        layout.addWidget(self.webview)
        layout.setStretchFactor(self.webview, 1)

        self.info_panel = infopanel.InfoPanel(self)
        layout.addWidget(self.info_panel)
        layout.setStretchFactor(self.info_panel, 0)

        self.editor = metadataeditor.MetadataEditor(self)
        layout.addWidget(self.editor)
        layout.setStretchFactor(self.editor, 0)

        self.entry_pages = datalib.generate_index_page(self.root_path,
                                        self.generated_index_path, data)
        self.goto_index()

        # Signals
        self.webview.next.connect(self.next)
        self.webview.previous.connect(self.previous)
        self.webview.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.webview.linkClicked.connect(self.link_clicked)
        self.webview.wheel_event.connect(self.wheel_event)
        self.editor.reload_index.connect(self.request_reload.emit)

        # Key shortcuts
        for key in data['hotkeys']['next']:
            common.set_hotkey(key, self, self.next)
        for key in data['hotkeys']['previous']:
            common.set_hotkey(key, self, self.previous)
        for key in data['hotkeys']['home']:
            common.set_hotkey(key, self, self.goto_index)
        for key in data['hotkeys']['toggle_fullscreen']:
            common.set_hotkey(key, self, self.toggle_fullscreen)


    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.info_panel.set_fullscreen(self.fullscreen, self.current_page)
        self.set_fullscreen.emit(self.fullscreen)


    def wheel_event(self, delta):
        # Negative delta means scrolling towards you
        if delta < 0:
            self.next()
        elif delta > 0:
            self.previous()


    def reload(self, data):
        self.entry_pages = datalib.generate_index_page(self.root_path,
                                    self.generated_index_path, data)
        if self.current_page == -1 \
                or not os.path.isfile(self.current_entry[self.current_page][0]):
            self.webview.reload()
            self.current_entry = []

    def link_clicked(self, url):
        if not url.isLocalFile():
            import webbrowser
            webbrowser.open_new_tab(url.toString())
        else:
            rawurl = url.toString()
            ext = os.path.splitext(rawurl)[1]
            if ext == '.json':
                self.editor.activate(url.toLocalFile())
            elif os.path.basename(rawurl) == 'start_here.sapfo':
                self.start_entry(os.path.dirname(rawurl))

    def start_entry(self, path):
        self.current_entry = self.entry_pages[os.path.basename(path)]
        # print('\n'.join(x for x,_ in self.current_entry))
        self.current_page = 0
        self.set_page()

    def next(self):
        if not self.current_entry:
            return
        if self.current_page < len(self.current_entry)-1:
            self.current_page += 1
            self.set_page()
        elif self.current_page == len(self.current_entry)-1:
            self.goto_index()

    def previous(self):
        if not self.current_entry:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.set_page()
        elif self.current_page == 0:
            self.goto_index()
        elif self.current_page == -1:
            self.current_page = len(self.current_entry)-1
            self.set_page()

    def set_page(self):
        newpath = self.current_entry[self.current_page][0]
        if not os.path.isfile(newpath):
            self.request_reload.emit()
            self.goto_index()
        else:
            self.webview.load(QtCore.QUrl.fromLocalFile(newpath))
            if self.info_panel.isHidden():
                self.info_panel.show()
            self.info_panel.set_info(self.current_entry, self.current_page)

    def goto_index(self):
        self.current_page = -1
        self.webview.load(QtCore.QUrl.fromLocalFile(self.generated_index_path))
        self.info_panel.hide()
