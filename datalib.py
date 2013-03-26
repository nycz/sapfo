import hashlib
import os
import os.path
from os.path import join
import re

from PyQt4 import QtCore

from libsyntyche import common


def generate_index_page(root_path, generated_index_path, data):
    """
    Create an index page with all stories in the instance's directory and
    return a list of all pages.

    root_path - the path to where all stories' directories are
    generated_index_path - where the generated index page is to be saved
    data - the data from settings.json including blacklist and name_filter
    """
    fname_rx = re.compile(data['name_filter'], re.IGNORECASE)
    entry_page_list = _get_all_stories_with_pages(root_path, fname_rx,
                                                  data['blacklist'])

    entries = [_get_entry_data(root_path, d, entry_page_list)\
               for d in os.listdir(root_path)
               if os.path.isdir(join(root_path, d))]
    html_template = common.read_file(common.local_path('index_page_template.html'))
    entry_template = common.read_file(common.local_path('entry_template.html'))
    formatted_entries = [_format_entry(entry_template, **data) \
            for data in sorted(entries, key=lambda x:x['title'])]
    common.write_file(generated_index_path, html_template.format(\
                        body='\n<hr />\n'.join(formatted_entries),
                        css=common.read_file(common.local_path('index_page.css'))))
    return entry_page_list


def _get_entry_data(root_path, path, entry_page_list):
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

def _format_entry(template, title, desc, tags, edit_url, start_link, page_count):
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


def _get_all_stories_with_pages(root_path, fname_rx, blacklist):
    """
    Return all stories as a dict.

    { storyname: [pages] }
    """
    return {
        d: _generate_page_links(join(root_path, d),
                               fname_rx, blacklist) \
        for d in os.listdir(root_path)
        if os.path.isdir(join(root_path,d))
    }




def _generate_page_links(path, name_rx, blacklist):
    """
    Return a list of all pages in the directory.
    [(filepath, subdir), (filepath2, subdir), ...]

    Files in the root directory should always be loaded first, then files in
    the subdirectories.
    """
    blacklist.append('metadata.json')

    def in_blacklist(name):
        for b in blacklist:
            if (b.startswith('$RX:') and re.search(b[4:], name)) \
                    or name == b:
                return True
        return False

    # name_rx = re.compile(name_filter)
    files = []
    if '.' not in blacklist:
        files = [(f, '') for f in sorted(os.listdir(path))
                 if os.path.isfile(join(path, f))\
                 and name_rx.search(f) and not in_blacklist(f)]

    dirs = [d for d in os.listdir(path)
            if os.path.isdir(join(path, d))\
            and d not in blacklist]

    for d in sorted(dirs):
        files.extend([(join(d,f),d) for f in sorted(os.listdir(join(path, d)))
                      if os.path.isfile(join(path, d, f))\
                      and name_rx.search(f)\
                      and not in_blacklist(d + '/' + f)])

    # print(len(files))
    return [(join(path, f), subdir) for f,subdir in files]
