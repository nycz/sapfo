import hashlib
import os
import os.path
from os.path import join

from PyQt4 import QtCore

import common


def generate_index_page(root_path, generated_index, entry_page_list):
    entries = [get_entry_data(root_path, x, entry_page_list)\
               for x in os.listdir(root_path)
               if os.path.isdir(join(root_path,x))]

    html_template = common.read_file('index_page_template.html')
    entry_template = common.read_file('entry_template.html')

    formatted_entries = [format_entry(entry_template, **data) \
            for data in sorted(entries, key=lambda x:x['title'])]

    common.write_file(generated_index, html_template.format(\
                        body='\n<hr />\n'.join(formatted_entries),
                        css=common.read_file('index_page.css')))


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
        files.extend([(join(d,f),d) for f in sorted(os.listdir(join(path, d)))
                      if os.path.isfile(join(path, d, f))\
                      and name_rx.search(f)\
                      and d + '/' + f not in blacklist])
    # print(len(files))
    return [(join(path, f), subdir) for f,subdir in files]
