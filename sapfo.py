#!/usr/bin/env python3

import os
import os.path
from os.path import join
import re
import sys

from PyQt4 import QtCore, QtGui, QtWebKit

import common
from common import read_file, write_file
import downloaddialog
import infopanel
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sapfo')

        download_window = downloaddialog.DownloadDialog()

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.tab_widget = QtGui.QTabWidget(self)
        layout.addWidget(self.tab_widget)

        instances = common.read_json('settings.json')
        for name, data in instances.items():
            self.tab_widget.addTab(ViewerFrame(name, data), name)

        # vert_layout = QtGui.QVBoxLayout(self)
        # vert_layout.setMargin(0)
        # vert_layout.setSpacing(0)
        # self.story_info_panel = infopanel.InfoPanel() #QtWebKit.QWebView()#
        # self.story_info_panel.hide()
        # vert_layout.addWidget(self.story_info_panel)
        # vert_layout.setStretchFactor(self.story_info_panel, 0)

        # self.webview = WebView()
        # vert_layout.addWidget(self.webview)
        # vert_layout.setStretchFactor(self.webview, 1)

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.reload)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, self.reload)
        # self.webview.urlChanged.connect(self.url_changed)

        self.setStyleSheet(read_file('qt.css'))
        self.show()

    # def url_changed(self, url):
    #     if url.toString().endswith('index_page_generated.html'):
    #         self.story_info_panel.hide()
    #     else:
    #         self.story_info_panel.show()

    def reload(self):
        self.setStyleSheet(read_file('qt.css'))
        self.tab_widget.currentWidget().reload()


def main():
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
