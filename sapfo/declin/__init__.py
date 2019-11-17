from pathlib import Path
from typing import Dict, NamedTuple

from . import parsing
from .common import ParsingError, Pos


StyleSpec = parsing.StyleSpec
Section = parsing.Section
ItemSection = parsing.ItemSection
LineSection = parsing.LineSection
ContainerSection = parsing.ContainerSection


class Model(NamedTuple):
    main: str
    sections: Dict[str, parsing.Section]


def parse(code: str) -> Model:
    chunks = parsing.text_to_chunks(code)
    default_style = parsing.parse_default(chunks.default)
    main_target = parsing.parse_export(chunks.export)
    # Parse the chunks
    sections: Dict[str, parsing.Section] = {}
    for chunk in chunks.sections:
        if not chunk:
            continue
        pos, cmd_line = chunk[0]
        name, section = parsing.parse_section(chunk, default_style)
        if name in sections:
            raise ParsingError(f'section name {name!r} already in use',
                               Pos(cmd_line, pos))
        sections[name] = section
    if not sections:
        raise ParsingError('no sections defined')
    return Model(main_target, sections)


if __name__ == '__main__':
    try:
        parse((Path(__file__).resolve().parent.parent
               / 'data' / 'entry_layout.gui'
               ).read_text())
    except ParsingError as e:
        print(f'\x1b[1;31mError:\x1b[0m {e.message}')
        if e.pos:
            print(f'On line {e.pos.line_num}:   {e.pos.line_text}')
