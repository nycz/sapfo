import enum
import re
from typing import Any, Collection, Dict, List, NamedTuple, Optional, Union


class ParsingError(Exception):
    pass


def _expand_macros(string: str, macros: Dict[str, str]) -> str:
    while True:
        str_macros = re.findall('@[^(),|]+', string)
        if not str_macros:
            break
        for m in str_macros:
            mname = m.strip().lstrip('@')
            if mname not in macros:
                raise ParsingError('Unknown tag macro')
            else:
                string = string.replace(m, '(' + macros[mname] + ')')
    return string


class TokenType(enum.Enum):
    START_GROUP = enum.auto()
    START_NEG_GROUP = enum.auto()
    END_GROUP = enum.auto()
    AND = enum.auto()
    OR = enum.auto()
    NAME = enum.auto()


class Token(NamedTuple):
    type_: TokenType
    lexeme: str


def _tokenize(string: str) -> List[Token]:
    """
    Create a list of tokens from the string of a command.
    The tokens are single chars such as (),| or tags.
    """
    TT = TokenType
    special_characters = {
        '(': TT.START_GROUP,
        ')': TT.END_GROUP,
        ',': TT.AND,
        '|': TT.OR,
    }
    START_GROUPS = {TT.START_GROUP, TT.START_NEG_GROUP}
    INVERT = '-'
    nospace = re.sub(r'\s*([(),|])\s*', r'\1', string)
    tokens = [Token(TT.START_GROUP, '(')]
    buf = ''
    for c in nospace:
        if c in special_characters.keys():
            # The new character is a special one, which ends the last token
            c_type = special_characters[c]
            if buf:
                # Change into negative group if preceded by a -
                if c_type is TT.START_GROUP and buf == INVERT:
                    c_type = TT.START_NEG_GROUP
                # Add the last token if we have one
                elif c_type is TT.START_GROUP:
                    # Only valid non-special char before a new group
                    # is the semi-special - char
                    raise ParsingError('Invalid syntax: invalid starting '
                                       'parenthesis')
                elif buf == INVERT:
                    # Can't filter on a lonely -
                    raise ParsingError(f'Invalid syntax: can\'t have a lone '
                                       f'"{INVERT}"')
                else:
                    tokens.append(Token(TT.NAME, buf))
                buf = ''
            elif tokens[-1].type_ in special_characters.values():
                last_type = tokens[-1].type_
                if last_type is TT.END_GROUP and c_type in START_GROUPS:
                    raise ParsingError('Invalid syntax: a group can\'t start '
                                       'directly after another ended')
                if len(tokens) == 1 and c_type not in START_GROUPS:
                    raise ParsingError(f'Invalid syntax: "{c}" can\'t '
                                       f'appear at the start of the filter')
                if last_type in START_GROUPS and c_type is TT.END_GROUP:
                    raise ParsingError('Invalid syntax: can\'t have an '
                                       'empty group')
                if last_type is not TT.END_GROUP \
                        and c_type not in START_GROUPS:
                    raise ParsingError(f'Invalid syntax: "{c}" can\'t '
                                       f'follow "{tokens[-1].lexeme}"')
            tokens.append(Token(c_type, c))
        else:
            if tokens[-1].type_ is TT.END_GROUP:
                raise ParsingError(f'Invalid syntax: "{c}" can\'t follow '
                                   f'a closed group')
            buf += c
    if buf:
        tokens.append(Token(TT.NAME, buf))
    return tokens + [Token(TT.END_GROUP, ')')]


class Mode(enum.Enum):
    AND = ','
    OR = '|'


class Group:
    def __init__(self, mode: Optional[Mode], invert: bool,
                 content: List[Union['Group', str]]) -> None:
        self.mode = mode or Mode.OR
        self.content = content
        self.invert = invert

    def __repr__(self) -> str:
        invert_str = '(NOT) ' if self.invert else ''
        return (f'<{self.__class__.__name__}: {invert_str}'
                f'{self.mode} [{self.content}]>')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) \
            and self.mode == other.mode \
            and self.invert == other.invert \
            and self.content == other.content


def _read_from(tokens: List[Token]) -> Group:
    if not tokens:
        raise ParsingError('No tokens')
    TT = TokenType
    modes = {TT.AND: Mode.AND, TT.OR: Mode.OR}
    mode: Optional[Mode] = None
    groups: List[Union[Group, str]] = []
    opening_token = tokens.pop(0)
    if opening_token.type_ not in {TT.START_GROUP, TT.START_NEG_GROUP}:
        raise ParsingError(f'Invalid syntax: expected a group but got '
                           f'"{opening_token.lexeme}"')
    invert = opening_token.type_ is TT.START_NEG_GROUP
    while tokens:
        token = tokens.pop(0)
        if token.type_ is TT.END_GROUP:
            if len(groups) == 1 and isinstance(groups[0], Group):
                if invert:
                    groups[0].invert = invert != groups[0].invert
                return groups[0]
            else:
                return Group(mode, invert, groups)
        elif token.type_ is TT.START_GROUP \
                or token.type_ is TT.START_NEG_GROUP:
            # Re-add the token for peace of mind and consistency
            tokens.insert(0, token)
            groups.append(_read_from(tokens))
        elif token.type_ is TT.AND or token.type_ is TT.OR:
            new_mode = modes[token.type_]
            if mode is not None and mode is not new_mode:
                raise ParsingError('Invalid syntax: mixed separators')
            mode = new_mode
        elif token.type_ is TT.NAME:
            groups.append(token.lexeme)
        else:
            raise NotImplementedError
    raise ParsingError('Invalid syntax: group wasn\'t closed')


def _match(tag: str, oldtags: Collection[str]) -> bool:
    """
    See if the tag exists in oldtags.
    """
    negative = tag.startswith('-')
    tag = tag.lstrip('-')
    if '*' in tag:
        rx = re.compile(tag.replace('*', '.+')+'$')
        for t in oldtags:
            if rx.match(t):
                # If it exists and shouldn't be there, quit
                if negative:
                    return False
                # If it exists and should be there, move on to next tag
                else:
                    break
        else:
            # If it doesn't exist and should be there, quit
            if not negative:
                return False
    else:
        # If it's there and shouldn't, or isn't there but should be, quit
        if (negative and tag in oldtags) \
                or (not negative and tag not in oldtags):
            return False
    # Otherwise it's fine
    return True


def _parse(group: Group, oldtags: Collection[str]) -> bool:
    """
    Parse the actual command to see if it matches the tags.
    """
    def handle(item: Union[str, Group]) -> bool:
        if isinstance(item, str):
            return _match(item, oldtags)
        else:
            return _parse(item, oldtags)

    if group.mode is Mode.AND:
        return all(handle(sub_group)
                   for sub_group in group.content) != group.invert
    elif group.mode is Mode.OR:
        return any(handle(sub_group)
                   for sub_group in group.content) != group.invert
    else:
        raise ParsingError('Invalid expression')


def compile_tag_filter(string: str, macros: Dict[str, str]) -> Group:
    return _read_from(_tokenize(_expand_macros(string, macros)))


def match_tag_filter(tag_filter: Group, oldtags: Collection[str]) -> bool:
    return _parse(tag_filter, oldtags)
