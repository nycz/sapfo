#!/usr/bin/env python3

import os
import os.path
from os.path import join
import sys

from PyQt4 import QtCore, QtGui, QtWebKit

import common
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
        rawurl = url.toString()
        ext = os.path.splitext(rawurl)[1]
        if ext == '.json':
            os.startfile(os.path.normpath(rawurl))
        elif ext == '.html':
            self.setUrl(url)
        # url.setUrl(url.toString().replace('edit_url', 'file'))

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

    with open('index_page_template.html', encoding='utf-8') as f:
        html_template = f.read()
    with open('index_page.css', encoding='utf-8') as f:
        css = f.read()

    with open('index_page_generated.html', 'w', encoding='utf-8') as f:
        f.write(html_template.format(body='\n<hr />\n\t'.join(entries), css=css))


def generate_entry(root_path, path):
    entry_template = """\
<div class="list_entry">
    <a href="{link}" class="entry_link">{title}</a> {tags} <a href="{edit}" class="edit_link">\u270e</a>
    <div class="description">{desc}</div>
</div>"""
    metadata = common.read_json(join(root_path, path, path + '.json'))
    desc = metadata['description'] if metadata['description'] else "<em>[no desc]</em>"
    first_page_link = join(root_path, path ,
            get_first_page_relative_url(root_path, path)).replace('\\', '/')
    first_page_link = QtCore.QUrl.fromLocalFile(first_page_link).toString()
    tags = ['<span class="tag">{}</span>'.format(x) for x in sorted(metadata['tags'])]
    edit_url = QtCore.QUrl.fromLocalFile(join(root_path, path, path + '.json'))
    # edit_url = edit_url.toString().replace('file://', 'edit_url://')
    # print(edit_url)
    return entry_template.format(link=first_page_link, title=path, desc=desc,
             tags=', '.join(tags), edit=edit_url.toString())


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
