import re

def _tokenize(string):
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
                if c == '(':
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

def _read_from(tokens):
    """
    Parse the tokens and return a nested list of ANDs and ORs and tags.
    """
    if not tokens:
        raise SyntaxError('No tokens')
    mode = None
    modes = {',':'AND', '|':'OR'}
    token = tokens.pop(0)
    if token == '(':
        parsedexp = []
        while tokens[0] != ')':
            subexp = _read_from(tokens)
            if subexp in (',', '|'):
                if mode is not None and modes[subexp] != mode:
                    raise SyntaxError('Mixed separators')
                mode = modes[subexp]
            else:
                parsedexp.append(subexp)
        tokens.pop(0)
        return [mode] + parsedexp
    elif token == ')':
        raise SyntaxError('Unexpected )')
    else:
        return token

def _match(tag, oldtags):
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
        if (negative and tag in oldtags) or (not negative and tag not in oldtags):
            return False
    # Otherwise it's fine
    return True

def compile_tag_filter(string):
    return _read_from(_tokenize(string))

def _parse(exp, oldtags):
    """
    Parse the actual command to see if it matches the tags.
    """
    def handle(x):
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


def parse_tag_filter(tag_filter, oldtags):
    return _parse(tag_filter, oldtags)
