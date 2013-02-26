import json
import os.path
import re

from PyQt4 import QtGui


def read_json(path):
    return json.loads(read_file(path))

def write_json(path, data):
    write_file(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

def read_file(path):
    with open(path, encoding='utf-8') as f:
        data = f.read()
    return data

def write_file(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(data)

def kill_theming(layout):
    layout.setMargin(0)
    layout.setSpacing(0)

def set_hotkey(key, target, callback):
    QtGui.QShortcut(QtGui.QKeySequence(key), target, callback)

def read_qt_stylesheet(path):
    data = read_file(path)
    re_values = re.compile(r'^(?P<key>\$\S+?)\s*:\s*(?P<value>\S+?);?$',
                           re.MULTILINE)

    stylesheet = '\n'.join([l for l in data.splitlines()
                            if not l.startswith('$')])

    for key, value in re_values.findall(data):
        stylesheet = stylesheet.replace(key, value)

    return stylesheet
