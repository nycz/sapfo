import json
import os.path

def read_json(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        data = f.read()
    if not data:
        return None
    else:
        return json.loads(data)

def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
