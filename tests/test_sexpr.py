"""Reader tests: tokenizing and parsing into numbers, symbols, strings, lists."""

import pytest

from prism.sexpr import Symbol, SexprError, parse, read_number


def test_number_literals_read_as_floats():
    assert parse("260") == [260.0]
    assert parse("-45") == [-45.0]
    assert parse("2/3") == [pytest.approx(2 / 3)]
    assert parse("0.5 .25") == [0.5, 0.25]


def test_read_number_rejects_non_numbers():
    assert read_number("L1") is None
    assert read_number("-points") is None
    assert read_number("1/0") is None  # division by zero
    assert read_number("1/2/3") is None


def test_bare_atoms_read_as_symbols():
    (form,) = parse("(add horizon 1/3)")
    assert form[0] == Symbol("add")
    assert form[1] == Symbol("horizon")
    assert form[2] == pytest.approx(1 / 3)


def test_string_literal_is_distinct_from_symbol():
    (string,) = parse('"A"')
    assert string == "A" and not isinstance(string, Symbol)
    (symbol,) = parse("A")
    assert symbol == Symbol("A") and isinstance(symbol, Symbol)


def test_quote_reader_macro_expands():
    assert parse("'P1") == [[Symbol("quote"), Symbol("P1")]]
    assert parse("'(a b)") == [[Symbol("quote"), [Symbol("a"), Symbol("b")]]]


def test_comments_and_multiple_forms():
    forms = parse("(list) ; inline comment\n(help)")
    assert forms == [[Symbol("list")], [Symbol("help")]]


@pytest.mark.parametrize("bad", ["(add", ")", "\"unterminated", "'"])
def test_malformed_input_raises(bad):
    with pytest.raises(SexprError):
        parse(bad)
