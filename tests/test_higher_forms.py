"""Higher-form tests: arithmetic, range, list, lambda, map, fold, application."""

from prism.items import LineItem


def val(interp, cmd):
    out, ok = interp.run(cmd)
    assert ok, f"expected {cmd!r} to succeed, got: {out!r}"
    return out


def err(interp, cmd):
    out, ok = interp.run(cmd)
    assert not ok, f"expected {cmd!r} to fail, got: {out!r}"
    return out


def test_arithmetic(interp):
    assert val(interp, "(+ 1 2 3)") == "6"
    assert val(interp, "(- 10 3 2)") == "5"
    assert val(interp, "(- 5)") == "-5"
    assert val(interp, "(* 2 3 4)") == "24"
    assert val(interp, "(/ 12 2 3)") == "2"
    assert val(interp, "(/ 4)") == "0.25"  # unary is reciprocal
    assert "divide by zero" in err(interp, "(/ 1 0)")
    assert "a number" in err(interp, "(+ 1 'A)")


def test_range_arities(interp):
    assert val(interp, "(range 5)") == "(0 1 2 3 4)"
    assert val(interp, "(range 2 5)") == "(2 3 4)"
    assert val(interp, "(range 0 1 5)") == "(0 0.25 0.5 0.75 1)"  # linspace, inclusive
    assert val(interp, "(range 3 3 1)") == "(3)"
    assert "at least 1" in err(interp, "(range 0 1 0)")


def test_list_constructor_and_nesting(interp):
    assert val(interp, "(list 1 2 3)") == "(1 2 3)"
    assert val(interp, "(list (+ 1 1) (* 2 3))") == "(2 6)"


def test_lambda_closes_over_environment(interp):
    val(interp, "(define k 10)")
    assert val(interp, "((lambda (x) (+ x k)) 5)") == "15"
    # Wrong arity is reported.
    assert "expects 1" in err(interp, "((lambda (x) x) 1 2)")


def test_map_builds_a_pencil(interp):
    val(interp, "(add horizon 1/3)")
    out = val(interp, "(map (lambda (t) (add line 250 (point 'L1 t))) (range 0 1 5))")
    assert out.count("L") == 5  # five new lines listed
    assert sum(isinstance(x, LineItem) for x in interp._lines()) == 6  # horizon + 5


def test_map_over_computed_angles(interp):
    val(interp, "(define V (add point 1/2 1/3))")
    val(interp, "(map (lambda (i) (add line (+ 250 (* i 10)) V)) (range 0 5))")
    assert len(interp._lines()) == 5


def test_fold_accumulates(interp):
    assert val(interp, "(fold + 0 (range 0 5))") == "10"
    assert val(interp, "(fold * 1 (range 1 5))") == "24"


def test_map_requires_a_list(interp):
    assert "must be a list" in err(interp, "(map (lambda (x) x) 5)")


def test_applying_a_non_procedure_errors(interp):
    assert "not something you can call" in err(interp, "(3 4)")


def test_builtins_are_shadowable_but_not_destroyed(interp):
    val(interp, "(define + 99)")   # user shadows the builtin in the session scope
    assert val(interp, "+") == "99"
    # A fresh interpreter still has the real +.
    from prism.commands import CommandInterpreter

    fresh = CommandInterpreter(interp.scene)
    assert fresh.run("(+ 1 1)")[0] == "2"
