"""Evaluator tests: environment, quoting, define/let, and the build forms."""

from prism.items import LineItem, PointItem


def ok(interp, cmd):
    out, good = interp.run(cmd)
    assert good, f"expected {cmd!r} to succeed, got: {out!r}"
    return out


def fails(interp, cmd):
    out, good = interp.run(cmd)
    assert not good, f"expected {cmd!r} to fail, but it succeeded: {out!r}"
    return out


def test_numbers_and_strings_self_evaluate(interp):
    assert interp.run("42")[0] == "42"
    assert interp.run("2/3")[0] == "0.666667"
    assert interp.run('"hello"')[0] == "hello"


def test_define_binds_and_persists_across_runs(interp):
    ok(interp, "(define A (add point 1/3 1/3))")
    # The binding survives into a later, separate run() call.
    ok(interp, "(add line 30 A)")
    assert len(interp._points()) == 1
    assert any(isinstance(x, LineItem) for x in interp._lines())


def test_bare_element_id_is_unbound(interp):
    ok(interp, "(add point 1/3 1/3)")
    out = fails(interp, "(add line 30 P1)")
    assert "Unbound name" in out


def test_quoting_resolves_an_element(interp):
    ok(interp, "(add point 1/3 1/3)")
    ok(interp, "(add line 30 'P1)")  # quoted id resolves to the element
    assert len(interp._lines()) == 1


def test_let_is_sequential_and_scoped(interp):
    ok(interp, "(add horizon 1/3)")
    # 't' is used by a later binding in the same let: sequential (let*).
    out = ok(interp, "(let ((t 2/3) (p (point 'L1 t))) p)")
    assert out.startswith("P")
    # The let-bound name does not leak into the top-level scope.
    assert "Unbound name" in fails(interp, "t")


def test_let_child_scope_does_not_mutate_parent(interp):
    ok(interp, "(define x 1/2)")
    ok(interp, "(let ((x 1/4)) x)")
    assert interp.run("x")[0] == "0.5"  # top-level x untouched


def test_nested_construction_still_builds(interp):
    ok(interp, "(add horizon 1/3)")
    ok(interp, "(add line 260 (point 'L1 2/3))")
    assert len(interp._lines()) == 2
    assert any(isinstance(x, PointItem) for x in interp._points())


def test_out_of_range_fraction_reports(interp):
    assert "between 0 and 1" in fails(interp, "(add point 2 2)")


def test_is_recordable(interp):
    assert interp.is_recordable("(define A (add point 1/3 1/3))")
    assert interp.is_recordable("(add horizon 1/3)")
    assert interp.is_recordable("(let ((t 1/3)) (add horizon t))")
    assert interp.is_recordable("(map (lambda (t) (add horizon t)) (range 0 1 3))")
    assert not interp.is_recordable("(show)")  # inspection, not building
    assert not interp.is_recordable("(help)")
