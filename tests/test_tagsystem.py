import pytest

from sapfo.tagsystem import (_expand_macros, _match, _tokenize,
                             compile_tag_filter, Group, match_tag_filter,
                             Mode, ParsingError, Token)
from sapfo.tagsystem import TokenType as TT


# Low level functions

@pytest.mark.parametrize(
    'text,tokens',
    [('a', [Token(TT.START_GROUP, '('),
            Token(TT.NAME, 'a'),
            Token(TT.END_GROUP, ')')]),
     ('(a)', [Token(TT.START_GROUP, '('),
              Token(TT.START_GROUP, '('),
              Token(TT.NAME, 'a'),
              Token(TT.END_GROUP, ')'),
              Token(TT.END_GROUP, ')')]),
     ('-(a)', [Token(TT.START_GROUP, '('),
               Token(TT.START_NEG_GROUP, '('),
               Token(TT.NAME, 'a'),
               Token(TT.END_GROUP, ')'),
               Token(TT.END_GROUP, ')')]),
     ('b, -(a | c)',
      [Token(TT.START_GROUP, '('),
       Token(TT.NAME, 'b'),
       Token(TT.AND, ','),
       Token(TT.START_NEG_GROUP, '('),
       Token(TT.NAME, 'a'),
       Token(TT.OR, '|'),
       Token(TT.NAME, 'c'),
       Token(TT.END_GROUP, ')'),
       Token(TT.END_GROUP, ')')]),
     ])
def test_tokenize(text, tokens):
    assert _tokenize(text) == tokens


@pytest.mark.parametrize(
    'group1,group2',
    [(Group(Mode.AND, False, ['a', 'b', 'c']),
      Group(Mode.AND, False, ['a', 'b', 'c'])),
     (Group(Mode.OR, True, ['a', Group(Mode.AND, True, ['b', 'c'])]),
      Group(Mode.OR, True, ['a', Group(Mode.AND, True, ['b', 'c'])]))])
def test_identical_groups(group1, group2):
    assert group1 == group2


@pytest.mark.parametrize(
    'group1,group2',
    [(Group(Mode.AND, False, ['a', 'b', 'c']),
      Group(Mode.AND, True, ['a', 'b', 'c'])),
     (Group(Mode.OR, True, ['a', 'b', 'c']),
      Group(Mode.AND, True, ['a', 'b', 'c'])),
     (Group(Mode.OR, True, ['a', 'b', 'c']),
      Group(Mode.OR, True, ['a', 'bar', 'c'])),
     (Group(Mode.OR, True, ['a', 'b']),
      Group(Mode.OR, True, ['a', 'b', 'c'])),
     (Group(Mode.OR, True, ['a', 'c', 'b']),
      Group(Mode.OR, True, ['a', 'b', 'c'])),
     (Group(Mode.OR, True, ['a', Group(Mode.OR, True, ['b', 'c'])]),
      Group(Mode.OR, True, ['a', Group(Mode.AND, True, ['b', 'c'])]))])
def test_not_identical_groups(group1, group2):
    assert group1 != group2


# Main functions

@pytest.mark.parametrize(
    'input_filter,wanted_group',
    [('a, b, c', Group(Mode.AND, False, ['a', 'b', 'c'])),
     ('a | b | c', Group(Mode.OR, False, ['a', 'b', 'c'])),
     ('a|b| c | ', Group(Mode.OR, False, ['a', 'b', 'c'])),
     ('a,b,c,', Group(Mode.AND, False, ['a', 'b', 'c'])),
     ('a | (foo,bar) | c', Group(Mode.OR, False,
                                 ['a', Group(Mode.AND, False,
                                             ['foo', 'bar']), 'c'])),
     ('a | (foo,bar) | c', Group(Mode.OR, False,
                                 ['a', Group(Mode.AND, False,
                                             ['foo', 'bar']), 'c'])),
     ('a', Group(Mode.OR, False, ['a'])),
     ('(a)', Group(Mode.OR, False, ['a'])),
     ('((((a))))', Group(Mode.OR, False, ['a'])),
     ('-a', Group(Mode.OR, False, ['-a'])),
     ('-(a)', Group(Mode.OR, True, ['a'])),
     ('-(a | b)', Group(Mode.OR, True, ['a', 'b'])),
     ]
)
def test_compile(input_filter, wanted_group):
    compiled = compile_tag_filter(input_filter, {})
    assert compiled == wanted_group


@pytest.mark.parametrize(
    'tag,tags,should_match',
    [('a', {'a', 'b', 'c'}, True),
     ('d', {'a', 'c'}, False),
     ('-a', {'a', 'c'}, False),
     ('a', set(), False),
     ('-a', set(), True),
     ('x*', {'xerxes', 'arst'}, True),
     ('-x*', {'xerxes', 'arst'}, False),
     ('x*', {'x', 'arst'}, False),
     ])
def test_match(tag, tags, should_match):
    assert _match(tag, tags) == should_match


def test_expand_macros():
    base = 'a, b, {}, c'
    macro = 'foo | bar | (x, y)'
    assert _expand_macros(base.format('@macaron'),
                          {'macaron': macro}) == base.format(f'({macro})')


@pytest.mark.parametrize(
    'filter_str,tags,should_match',
    [('a, b, c', {'a', 'b', 'c'}, True),
     ('a, b, c', {'a', 'c'}, False),
     ('a | b | c', {'a', 'c'}, True),
     ('-a | b | c', {'a', 'c'}, True),
     ('-a', {'a', 'c'}, False),
     ('-(a | b)', {'j', 'x'}, True),
     ('-(a | b)', {'a', 'c'}, False),
     ('a', set(), False),
     ('-a', set(), True),
     ('-a', {'a'}, False),
     ('-a', {'b'}, True),
     ('(a, b) | x', {'b'}, False),
     ('(a, b) | x', {'j', 'x'}, True),
     ('-(a, b) | c', {'a', 'x'}, True),
     ('-(a, b) | c', {'a', 'b', 'arst'}, False),
     ])
def test_whole_pipeline(filter_str, tags, should_match):
    tag_filter = compile_tag_filter(filter_str, {})
    assert match_tag_filter(tag_filter, tags) == should_match


# Assert errors

@pytest.mark.parametrize(
    'text',
    ['()', '(()', 'abc (foo bar)', 'ahh,|xx ', '), foo', '(a, b)- n',
     'arst || boo'])
def test_tokenize_errors(text):
    with pytest.raises(ParsingError):
        _tokenize(text)


@pytest.mark.parametrize(
    'filter_str',
    ['(abc', 'a, b | c', '@missing'])
def test_compile_errors(filter_str):
    with pytest.raises(ParsingError):
        compile_tag_filter(filter_str, {})
