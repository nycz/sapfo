from pathlib import Path
from typing import Dict, NamedTuple

from ..taggedlist import Attr
from . import parsing
from .common import ParsingError, Pos

StyleSpec = parsing.StyleSpec
Section = parsing.Section
ItemSection = parsing.ItemSection
LineSection = parsing.LineSection
ContainerSection = parsing.ContainerSection


class Model(NamedTuple):
    main: str
    attributes: Dict[str, Attr]
    sections: Dict[str, parsing.Section]


def parse(base_code: str, *overrides: str) -> Model:
    chunks = parsing.text_to_chunks(base_code)
    if chunks.default is None:
        raise ParsingError('missing DEFAULT section')
    if chunks.export is None:
        raise ParsingError('missing EXPORT section')
    # TODO: include the file in the error messages maybe
    for override in overrides:
        extra_chunks = parsing.text_to_chunks(override)
        if extra_chunks.default is not None:
            chunks.default.extend(extra_chunks.default[1:])
        if extra_chunks.export is not None:
            chunks.export.extend(extra_chunks.export[1:])
        if extra_chunks.sections:
            # section name: section data
            updated_sections = {s[0][1].split(None, 1)[1]: s
                                for s in extra_chunks.sections if s}
            for raw_section in chunks.sections:
                if not raw_section:
                    continue
                name = raw_section[0][1].split(None, 1)[1]
                if name in updated_sections:
                    # Don't include the def line when appending this
                    raw_section.extend(updated_sections.pop(name)[1:])
            chunks.sections.extend(updated_sections.values())
    default_style = parsing.parse_default(chunks.default)
    main_target = parsing.parse_export(chunks.export)
    # Parse the attributes
    attributes: Dict[str, Attr] = {}
    for chunk in chunks.attributes:
        if not chunk:
            continue
        pos, cmd_line = chunk[0]
        name, attr = parsing.parse_attribute(chunk)
        if name in attributes:
            raise ParsingError(f'attribute name {name!r} already in use',
                               Pos(cmd_line, pos))
        attributes[name] = attr
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
    return Model(main_target, attributes, sections)


if __name__ == '__main__':
    try:
        parse((Path(__file__).resolve().parent.parent
               / 'data' / 'entry_layout.gui'
               ).read_text())
    except ParsingError as e:
        print(f'\x1b[1;31mError:\x1b[0m {e.message}')
        if e.pos:
            print(f'On line {e.pos.line_num}:   {e.pos.line_text}')
