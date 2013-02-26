#!/usr/bin/env python3

import colorsys
import hashlib
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
            self.tab_widget.addTab(WebView(name, data), name)

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


class WebView(QtWebKit.QWebView):
    def __init__(self, title, data):
        super().__init__()
        self.title = title
        self.root_path = os.path.normpath(data['path'])
        self.generated_index = join(self.root_path,
                    'index_page_generated_{}.html'.format(title))
        self.fname_rx = re.compile(data['name_filter'], re.IGNORECASE)
        self.entry_pages = {d:generate_page_links(join(self.root_path, d),
                                                self.fname_rx,
                                                data['blacklist'])\
                            for d in os.listdir(self.root_path)
                            if os.path.isdir(join(self.root_path,d))}
        # print(self.entry_pages)
        self.current_entry = []
        self.current_page = -1

        generate_index_page(self.root_path, self.generated_index, self.entry_pages)
        self.goto_index()

        QtGui.QShortcut(QtGui.QKeySequence("N"), self, self.next)
        QtGui.QShortcut(QtGui.QKeySequence("P"), self, self.previous)

        self.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.linkClicked.connect(self.link_clicked)

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
        self.setUrl(QtCore.QUrl.fromLocalFile(self.current_entry[self.current_page][0]))

    def goto_index(self):
        self.current_page = -1
        self.setUrl(QtCore.QUrl.fromLocalFile(self.generated_index))

    # Override
    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.XButton1:
            self.previous()
        elif ev.button() == QtCore.Qt.XButton2:
            self.next()
        else:
            super().mouseReleaseEvent(ev)

    # Override
    def reload(self):
        if self.url() == QtCore.QUrl.fromLocalFile(self.generated_index):
            generate_index_page(self.root_path, self.generated_index, self.entry_pages)
        super().reload()


def generate_index_page(root_path, generated_index, entry_page_list):
    entries = [get_entry_data(root_path, x, entry_page_list)\
               for x in os.listdir(root_path)
               if os.path.isdir(join(root_path,x))]

    html_template = read_file('index_page_template.html')
    entry_template = read_file('entry_template.html')

    formatted_entries = [format_entry(entry_template, **data) \
            for data in sorted(entries, key=lambda x:x['title'])]

    write_file(generated_index, html_template.format(\
                        body='\n<hr />\n'.join(formatted_entries),
                        css=read_file('index_page.css')))


def get_entry_data(root_path, path, entry_page_list):
    """
    Return a dict with all relevant data from an entry.

    No formatting or theming!
    """
    metadata_path = join(root_path, path, 'metadata.json')
    try:
        metadata = common.read_json(metadata_path)
    except:
        metadata = {
            "description": "",
            "tags": [],
            "title": path
        }
        common.write_json(metadata_path, metadata)
    start_link = join(root_path, path, 'start_here.sapfo')
    return {
        'title': metadata['title'],
        'desc': metadata['description'],
        'tags': metadata['tags'],
        'edit_url': QtCore.QUrl.fromLocalFile(metadata_path).toString(),
        'start_link': QtCore.QUrl.fromLocalFile(start_link).toString(),
        'page_count': len(entry_page_list[path])
    }

def format_entry(template, title, desc, tags, edit_url, start_link, page_count):
    """
    Return the formatted entry as a html string.
    """
    desc = desc if desc else '<span class="empty_desc">[no desc]</span>'

    tag_template = '<span class="tag" style="background-color:{color};">{tag}</span>'
    tags = [tag_template.format(color=tag_color(x),tag=x)\
            for x in sorted(tags)]

    return template.format(
        link=start_link,
        title=title,
        desc=desc,
        tags=''.join(tags),
        edit=edit_url,
        page_count='({} pages)'.format(page_count) if page_count != 1 else ''
    )



def tag_color(text):
    md5 = hashlib.md5()
    md5.update(bytes(text, 'utf-8'))
    hashnum = int(md5.hexdigest(), 16)
    r = (hashnum & 0xFF0000) >> 16
    g = (hashnum & 0x00FF00) >> 8
    b = (hashnum & 0x0000FF)
    # h = int(((hashnum & 0xFF00) >> 8) / 256 * 360)
    # s = (hashnum & 0xFF) / 256
    # l = 0.5
    # return 'hsl({h}, {s:.0%}, {l:.0%})'.format(h=h, s=s, l=l)
    return 'rgb({r}, {g}, {b})'.format(r=r, g=g, b=b)


def generate_page_links(path, name_rx, blacklist):
    """
    Return a list of all pages in the directory.

    Files in the root directory should always be loaded first, then files in
    the subdirectories.
    """
    # name_rx = re.compile(name_filter)
    files = []
    if '.' not in blacklist:
        files = [(f, '') for f in sorted(os.listdir(path))
                 if os.path.isfile(join(path, f))\
                 and name_rx.search(f) and f not in blacklist]

    dirs = [d for d in os.listdir(path)
            if os.path.isdir(join(path, d))\
            and d not in blacklist]

    for d in sorted(dirs):
        files.extend([(join(f,d),d) for f in sorted(os.listdir(join(path, d)))
                      if os.path.isfile(join(path, d, f))\
                      and name_rx.match(f)\
                      and d + '/' + f not in blacklist])
    # print(len(files))
    return [(join(path, f), subdir) for f,subdir in files]




def main():
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
