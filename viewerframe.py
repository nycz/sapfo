import os
import os.path
from os.path import join
import re

from PyQt4 import QtCore, QtGui, QtWebKit

import common
import datalib


class ViewerFrame(QtGui.QFrame):

    class WebView(QtWebKit.QWebView):
        previous = QtCore.pyqtSignal()
        next = QtCore.pyqtSignal()
        # Overrides
        def reload(self):
            if self.url() == QtCore.QUrl.fromLocalFile(self.generated_index):
                datalib.generate_index_page(self.root_path, self.generated_index,
                                    self.entry_pages)
            super().reload()

        def mouseReleaseEvent(self, ev):
            if ev.button() == QtCore.Qt.XButton1:
                self.previous.emit()
            elif ev.button() == QtCore.Qt.XButton2:
                self.next.emit()
            else:
                super().mouseReleaseEvent(ev)


    def __init__(self, title, data):
        super().__init__()
        self.title = title
        self.root_path = os.path.normpath(data['path'])
        self.generated_index = join(self.root_path,
                    'index_page_generated_{}.html'.format(title))
        self.fname_rx = re.compile(data['name_filter'], re.IGNORECASE)
        self.entry_pages = {d:datalib.generate_page_links(join(self.root_path, d),
                                                self.fname_rx,
                                                data['blacklist'])\
                            for d in os.listdir(self.root_path)
                            if os.path.isdir(join(self.root_path,d))}

        self.current_entry = []
        self.current_page = -1

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)
        self.webview = self.WebView()
        layout.addWidget(self.webview)

        datalib.generate_index_page(self.root_path, self.generated_index,
                                    self.entry_pages)
        self.goto_index()

        self.webview.next.connect(self.next)
        self.webview.previous.connect(self.previous)

        QtGui.QShortcut(QtGui.QKeySequence("N"), self, self.next)
        QtGui.QShortcut(QtGui.QKeySequence("P"), self, self.previous)

        self.webview.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.webview.linkClicked.connect(self.link_clicked)

    def reload(self):
        self.webview.reload()

    def link_clicked(self, url):
        if not url.isLocalFile():
            import webbrowser
            webbrowser.open_new_tab(url.toString())
        else:
            rawurl = url.toString()
            ext = os.path.splitext(rawurl)[1]
            if ext == '.json':
                os.startfile(os.path.normpath(rawurl))
            elif os.path.basename(rawurl) == 'start_here.sapfo':
                self.start_entry(os.path.dirname(rawurl))

    def start_entry(self, path):
        self.current_entry = self.entry_pages[os.path.basename(path)]
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
        self.webview.load(QtCore.QUrl.fromLocalFile(self.current_entry[self.current_page][0]))

    def goto_index(self):
        self.current_page = -1
        self.webview.load(QtCore.QUrl.fromLocalFile(self.generated_index))
