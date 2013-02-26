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


class MainWindow(QtWebKit.QWebView):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sapfo')

        download_window = downloaddialog.DownloadDialog()
        generate_index_page()

        self.setUrl(QtCore.QUrl('index_page_generated.html'))

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.reload)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, self.reload)

        self.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.linkClicked.connect(self.link_clicked)
        self.show()

    def link_clicked(self, url):
        if not url.isLocalFile():
            import webbrowser
            webbrowser.open_new_tab(url.toString())
        else:
            rawurl = url.toString()
            ext = os.path.splitext(rawurl)[1]
            if ext == '.json':
                os.startfile(os.path.normpath(rawurl))
            elif ext == '.html':
                self.setUrl(url)

    # Override
    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.XButton1:
            self.back()
        elif ev.button() == QtCore.Qt.XButton2:
            self.forward()
        else:
            super().mouseReleaseEvent(ev)

    # Override
    def reload(self):
        # ugly ugly UGLY hack
        if self.url().toString().endswith('index_page_generated.html'):
            generate_index_page()
        super().reload()

def generate_index_page():
    root_path = os.path.normpath(common.read_json('settings.json')['root_path'])

    ignorefiles = ['literoticadownloader.py', 'literoticatemplate.html']
    entries = [generate_entry(root_path, x) for x in os.listdir(root_path)
               if x not in ignorefiles and os.path.isdir(join(root_path,x))]

    html_template = read_file('index_page_template.html')
    css = read_file('index_page.css')

    write_file('index_page_generated.html',
            html_template.format(body='\n<hr />\n'.join(entries), css=css))


def generate_entry(root_path, path):
    entry_template = read_file('entry_template.html')

    metadata = common.read_json(join(root_path, path, path + '.json'))

    if metadata['description']:
        desc = metadata['description']
    else:
        desc = '<span class="empty_desc">[no desc]</span>'

    page_count = generate_page_count(join(root_path, path))

    first_page_link = join(root_path, path ,
            get_first_page_relative_url(root_path, path)).replace('\\', '/')
    first_page_link = QtCore.QUrl.fromLocalFile(first_page_link).toString()
    tags = ['<span class="tag" style="background-color:{color};">{tag}</span>'.format(color=tag_color(x),tag=x)\
            for x in sorted(metadata['tags'])]
    edit_url = QtCore.QUrl.fromLocalFile(join(root_path, path, path + '.json'))

    return entry_template.format(link=first_page_link, title=path, desc=desc,
             tags=''.join(tags), edit=edit_url.toString(), page_count=page_count)


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

def generate_page_count(path):
    dir_rx = re.compile(r'Ch\. \d\d$')

    items = os.listdir(path)
    files = [x for x in items
             if os.path.isfile(join(path, x)) \
             and os.path.splitext(x)[1] == '.html']

    page_count = len(files)

    dirs = [x for x in items
            if os.path.isdir(join(path, x)) \
            and dir_rx.match(x)]

    for d in dirs:
        sub_files = [x for x in os.listdir(join(path, d))
                     if os.path.isfile(join(path, d, x)) \
                     and os.path.splitext(x)[1] == '.html']
        page_count += len(sub_files)

    if page_count == 1:
        return ""

    if not dirs:
        return '({} pages)'.format(page_count)

    return '({} chapter{}, {} pages)'.format(len(dirs), 's'*(len(dirs)>1), page_count)


def get_first_page_relative_url(root_path, path):
    root_files = os.listdir(join(root_path, path))
    ext = '.html'
    pagenum = ' - Page 1'
    chapter = ' Ch. 01'
    if path + ext in root_files:
        return path + ext
    elif path + pagenum + ext in root_files:
        return path + pagenum + ext
    elif path + chapter + ext in root_files:
        return path + chapter + ext
    elif chapter.strip() in root_files and os.path.isdir(join(root_path, path, chapter.strip())):
        sub_files = os.listdir(join(root_path, path, chapter.strip()))
        if path + chapter + ext in sub_files:
            return join(chapter.strip(), path + chapter + ext)
        elif path + chapter + pagenum + ext in sub_files:
            return join(chapter.strip(), path + chapter + pagenum + ext)
    return '#'


def main():
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
