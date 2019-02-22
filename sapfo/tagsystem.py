import re
from typing import Any, Callable, Collection, Dict, List, Union


def _expand_macros(string: str, macros: Dict[str, str]) -> str:
    while True:
        str_macros = re.findall('@[^(),|]+', string)
        if not str_macros:
            break
        for m in str_macros:
            mname = m.strip().lstrip('@')
            if mname not in macros:
                raise SyntaxError('Unknown tag macro')
            else:
                string = string.replace(m, '(' + macros[mname] + ')')
    return string


def _tokenize(string: str) -> List[str]:
    """
    Create a list of tokens from the string of a command.
    The tokens are single chars such as (),| or tags.
    """
    nospace = re.sub(r'\s*([(),|])\s*', r'\1', string)
    tokens = ['(']
    buf = ''
    for c in nospace:
        if c in '(),|':
            if buf:
                if c == '(' and buf != '-':
                    raise SyntaxError('Invalid syntax: invalid starting parenthesis')
                tokens.append(buf)
                buf = ''
            else:
                t = tokens[-1]
                if (t == ')' and c == '(') or (t in '(,|' and c != '('):
                    raise SyntaxError('Invalid syntax: invalid parentheses')
            tokens.append(c)
        else:
            buf += c
    if buf:
        tokens.append(buf)
    return tokens + [')']


def _read_from(tokens: List[str], invert: bool = False) -> Any:
    """
    Parse the tokens and return a nested list of ANDs and ORs and tags.

    Also convert NOTs preceding parentheses to individual negative tags.
    """
    if not tokens:
        raise SyntaxError('No tokens')
    mode = None
    modes = {',': 'AND', '|': 'OR'}
    token = tokens.pop(0)
    if token == '-':
        token = tokens.pop(0)
        invert = not invert
    if token == '(':
        parsedexp = []
        while tokens[0] != ')':
            subexp = _read_from(tokens, invert)
            if subexp in (',', '|'):
                if mode is not None and modes[subexp] != mode:
                    raise SyntaxError('Mixed separators')
                mode = modes[subexp]
            else:
                parsedexp.append(subexp)
        tokens.pop(0)
        if invert:
            # invert mode
            mode = 'AND' if mode == 'OR' else 'OR'
        return [mode] + parsedexp
    elif token == ')':
        raise SyntaxError('Unexpected )')
    else:
        if invert and token not in (',', '|'):
            token = token[1:] if token.startswith('-') else '-'+token
        return token


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


def _parse(exp: List, oldtags: Collection[str]) -> bool:
    """
    Parse the actual command to see if it matches the tags.
    """
    def handle(x: Union[str, List]) -> Callable[[Any, Collection[str]], bool]:
        """ Match x if it's a tag, otherwise parse it as an expression """
        return (_match if isinstance(x, str) else _parse)(x, oldtags)

    if exp[0] is None and len(exp) == 2:
        return handle(exp[1])
    elif exp[0] == 'AND':
        for e in exp[1:]:
            if not handle(e):
                return False
        return True
    elif exp[0] == 'OR':
        for e in exp[1:]:
            if handle(e):
                return True
        return False
    else:
        raise SyntaxError('Invalid expression')


def compile_tag_filter(string: str, macros: Dict[str, str]) -> Any:
    return _read_from(_tokenize(_expand_macros(string, macros)))


def match_tag_filter(tag_filter: Any, oldtags: Collection[str]) -> bool:
    return _parse(tag_filter, oldtags)
