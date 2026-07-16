"""Infinite points: parallel-line families that share a direction."""

import math

from PySide6.QtCore import QPointF

from prism import scene_state
from prism.infinity import InfinitePoint, normalize_angle


def line_angle(line) -> float:
    """A line's direction in degrees, folded into [0, 180)."""
    d = line.scene_direction()
    return round(math.degrees(math.atan2(d.y(), d.x())) % 180.0, 3)


def family(interp):
    return [ln for ln in interp._lines() if ln.has_infinity()]


def ok(interp, cmd):
    out, good = interp.run(cmd)
    assert good, f"expected {cmd!r} to succeed, got: {out!r}"
    return out


def fails(interp, cmd):
    out, good = interp.run(cmd)
    assert not good, f"expected {cmd!r} to fail, got: {out!r}"
    return out


def test_angle_normalization_mod_180():
    assert normalize_angle(30) == 30
    assert normalize_angle(210) == 30      # opposite direction, same ideal point
    assert normalize_angle(-45) == 135
    assert InfinitePoint(200).angle == 20


def test_infinity_keyword_is_not_a_number():
    # 'infinity' must read as a symbol, not float('inf').
    from prism.sexpr import Symbol, parse, read_number

    assert read_number("infinity") is None
    assert read_number("inf") is None
    assert read_number("nan") is None
    assert parse("(add infinity 30)")[0][1] == Symbol("infinity")


def test_family_lines_are_parallel(interp):
    ok(interp, "(add infinity 30)")
    ok(interp, "(add line 'I1 (add point 1/3 1/3))")
    ok(interp, "(add line 'I1 (add point 2/3 2/3))")
    angles = {line_angle(ln) for ln in family(interp)}
    assert len(family(interp)) == 2
    assert angles == {30.0}


def test_orient_swings_the_whole_family(interp):
    ok(interp, "(add infinity 30)")
    ok(interp, "(add line 'I1 (add point 1/3 1/3))")
    ok(interp, "(add line 'I1 (add point 2/3 2/3))")
    ok(interp, "(orient 'I1 75)")
    assert {line_angle(ln) for ln in family(interp)} == {75.0}


def test_dragging_a_family_line_rotates_all(interp):
    ok(interp, "(add infinity 30)")
    ok(interp, "(add line 'I1 (add point 1/3 1/3))")
    ok(interp, "(add line 'I1 (add point 2/3 2/3))")
    a_line = family(interp)[0]
    pivot = a_line.pivot().center()
    a_line._rotate_about_pivot(QPointF(pivot.x() + 10, pivot.y() - 10))  # ~ -45°/135°
    angles = {line_angle(ln) for ln in family(interp)}
    assert len(angles) == 1 and angles != {30.0}  # all swung, still parallel


def test_moving_the_anchor_carries_the_line(interp):
    ok(interp, "(add infinity 0)")
    ok(interp, "(define P (add point 1/2 1/2))")
    ok(interp, "(add line 'I1 P)")
    line = family(interp)[0]
    before = line.scene_line().center()
    line.pivot().moveBy(40, 0)
    interp.scene.on_point_moved(line.pivot())
    assert line.scene_line().center() != before
    assert line_angle(line) == 0.0  # still horizontal


def test_binding_an_infinite_point(interp):
    ok(interp, "(define d (add infinity 10))")
    ok(interp, "(add line d (add point 1/2 1/2))")   # reference via binding
    assert line_angle(family(interp)[0]) == 10.0


def test_serialization_round_trips(interp):
    ok(interp, "(add infinity 30)")
    ok(interp, "(add line 'I1 (add point 1/3 1/3))")
    ok(interp, "(add line 'I1 (add point 2/3 2/3))")
    ok(interp, "(orient 'I1 75)")
    scene_state.restore(interp.scene, scene_state.capture(interp.scene))
    lines = family(interp)
    assert len(interp.scene.infinities()) == 1
    assert len(lines) == 2
    assert {line_angle(ln) for ln in lines} == {75.0}
    # Both lines link to the same restored infinite point.
    assert lines[0].infinity() is lines[1].infinity()


def test_errors(interp):
    ok(interp, "(add infinity 30)")
    ok(interp, "(add infinity 90)")
    assert "No infinite point" in fails(interp, "(orient 'I9 30)")
    # Two infinite points can't make a line — it needs a finite point to sit at.
    assert "finite point" in fails(interp, "(add line 'I1 'I2)")
