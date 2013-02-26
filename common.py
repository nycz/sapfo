import json
import os.path

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
