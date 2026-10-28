"""Command interpreter for the canvas console.

Commands are S-expressions, so they compose: a form's value can be fed
straight into another form.

    (add horizon 1/3)
    (add-line 260 P1)
    (add-line 260 (point L1 2/3))

Atoms are passed to each form as raw text and interpreted by that form (an
angle, a fraction, an element name); nested forms are evaluated first and yield
real elements. Forms return the element they create, which is what allows the
nesting above.
"""

import shiboken6

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from prism.items import LineItem, PointItem
from prism.sexpr import SexprError, parse


class CommandError(Exception):
    """A problem the user should see, phrased for them."""


class Lambda:
    """A function, made by ``(lambda (<params>) <body>)``.

    The body is kept **unevaluated** — the raw s-expressions the reader
    produced — and run afresh on each call, with the parameters bound to the
    arguments. ``scope`` is the stack of frames in force where the lambda was
    written, so a lambda made inside another call still sees that call's
    parameters when it runs later.
    """

    def __init__(self, params: list, body: list, scope: list, name: str = None):
        self.params = params
        self.body = body
        self.scope = scope
        #: Set by ``(define …)``, so messages can name the function.
        self.name = name

    def described(self) -> str:
        """How the function reads back, e.g. ``(lambda (q) …)``."""
        return f"(lambda ({' '.join(self.params)}) …)"

    def __repr__(self) -> str:
        return f"<Lambda {self.name or '?'}({', '.join(self.params)})>"


def parse_fraction(text: str) -> float | None:
    """Read a 0-1 position written as a fraction or a decimal.

    Accepts forms like ``1/2``, ``2/3``, ``0.5`` or ``.25``.

    Returns:
        The value, or None if it can't be read.
    """
    text = str(text).strip()
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 2:
            return None
        try:
            numerator, denominator = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if denominator == 0:
            return None
        return numerator / denominator
    try:
        return float(text)
    except ValueError:
        return None


class CommandInterpreter:
    def __init__(self, scene):
        self.scene = scene
        #: Names bound with ``(define …)``. A name shadows a label of the
        #: same text, since you chose it deliberately.
        self._variables: dict = {}
        #: Parameter frames, innermost last, while a lambda is running.
        self._scope: list = []
        #: How many calls are running. Counted apart from the scope stack,
        #: which a closure *replaces* rather than extends, so it would never
        #: grow for a function that calls itself.
        self._depth = 0
        self._forms = {
            "add": self._form_add,
            "clear": self._form_clear,
            "add-line": self._form_add_line,
            "point": self._form_point,
            "rm": self._form_rm,
            "hide": self._form_hide,
            "show": self._form_show,
            "label": self._form_label,
            "format": self._form_format,
            "list": self._form_list,
            "ls": self._form_ls,
            "define": self._form_define,
            "lambda": self._form_lambda,
            "map": self._form_map,
            "draw-triangle": self._form_draw_triangle,
            "draw-cevians": self._form_draw_cevians,
            "points": self._form_points,
            "lines": self._form_lines,
            "meets": self._form_meets,
            "lines-through": self._form_lines_through,
            "points-on": self._form_points_on,
            "points-off": self._form_points_off,
            "join": self._form_join,
            "diff": self._form_diff,
            "intersect": self._form_intersect,
            "without": self._form_without_moved,
            "take": self._form_take,
            "last": self._form_last,
            "repeat": self._form_repeat,
            "help": self._form_help,
        }

    # -- Entry point -------------------------------------------------------

    #: Forms that only inspect; they aren't worth recording into a script.
    NON_RECORDING = {
        "ls", "help", "points", "lines", "meets", "lines-through", "points-on",
        "points-off", "diff", "without", "intersect", "take", "last", "lambda",
    }

    def execute(self, text: str) -> str:
        """Run one or more forms and return the output text."""
        return self.run(text)[0]

    def run(self, text: str) -> tuple:
        """Run one or more forms.

        Returns:
            An ``(output, ok)`` pair, where ok is False if anything failed.
        """
        text = text.strip()
        if not text:
            return "", False
        try:
            expressions = parse(text)
        except SexprError as exc:
            return f"Syntax error: {exc}", False

        outputs = []
        for expression in expressions:
            try:
                value = self._eval(expression)
            except CommandError as exc:
                return str(exc), False
            except Exception as exc:  # keep the console alive on any error
                return f"Error: {exc}", False
            rendered = self._render(value)
            if rendered:
                outputs.append(rendered)
        return "\n".join(outputs), True

    def is_recordable(self, text: str) -> bool:
        """Whether a command is worth saving into a script (i.e. it builds)."""
        try:
            expressions = parse(text)
        except SexprError:
            return False
        for expression in expressions:
            if (
                isinstance(expression, list)
                and expression
                and isinstance(expression[0], str)
                and expression[0].lower() not in self.NON_RECORDING
            ):
                return True
        return False

    def variables(self) -> dict:
        """The names bound with ``(define …)``, as ``{name: value}``."""
        return dict(self._variables)

    def command_names(self):
        return sorted(self._forms)

    # -- Evaluation --------------------------------------------------------

    def _eval(self, expression):
        if not isinstance(expression, list):
            raise CommandError(
                f"Commands are wrapped in parentheses - try ({expression} ...). "
                "Type (help)."
            )
        if not expression:
            raise CommandError("Empty form ().")
        head = expression[0]
        if isinstance(head, list):
            # ((lambda (q) …) P1) — written out and called on the spot.
            return self._apply(self._eval(head), expression[1:], "that function")
        if not isinstance(head, str):
            raise CommandError("A form must start with a command name.")
        form = self._forms.get(head.lower())
        if form is not None:
            return form(expression[1:])
        # A built-in form wins over a name, so the language can't be shadowed.
        bound = self._lookup(head)
        if isinstance(bound, Lambda):
            return self._apply(bound, expression[1:], head)
        if bound is not None:
            raise CommandError(
                f"{head!r} names {self._describe(bound)}, which isn't a "
                "function, so it can't be called. Type (help)."
            )
        raise CommandError(f"Unknown command: {head!r}. Type (help).")

    def _value(self, argument):
        """Evaluate an argument.

        Nested forms run; a bare word that names a variable gives its value;
        anything else passes through as text for the form to interpret.
        """
        if isinstance(argument, list):
            return self._eval(argument)
        if isinstance(argument, str):
            bound = self._lookup(argument)
            if bound is not None:
                return bound
        return argument

    def _lookup(self, name: str):
        """A name's value, from the innermost scope that has it, or None.

        A lambda's parameters shadow a ``(define …)`` name, which in turn
        shadows a label — innermost wins, as in any lisp.
        """
        for frame in reversed(self._scope):
            if name in frame:
                return frame[name]
        if name in self._variables:
            return self._surviving(name)
        return None

    def _surviving(self, name: str):
        """A name's value, minus anything no longer on the canvas.

        A name outlives the elements it was bound to — clearing the canvas,
        or removing a point, leaves it holding something that is gone. Those
        are dropped on use, so a stale name shrinks rather than blowing up
        with an error from deep inside Qt.
        """
        value = self._variables[name]
        if isinstance(value, Lambda):
            return value
        if isinstance(value, list):
            kept = [item for item in value if _on_canvas(item)]
            if len(kept) != len(value):
                self._variables[name] = kept
            if not kept:
                raise CommandError(
                    f"Nothing named {name!r} is on the canvas any more."
                )
            return kept
        if not _on_canvas(value):
            del self._variables[name]
            raise CommandError(f"{name!r} is no longer on the canvas.")
        return value

    # -- Argument coercion -------------------------------------------------

    def _as_float(self, argument, what: str) -> float:
        value = self._value(argument)
        try:
            return float(value)
        except (TypeError, ValueError):
            raise CommandError(f"Couldn't read {value!r} as {what}.")

    def _as_fraction(self, argument) -> float:
        value = self._value(argument)
        fraction = parse_fraction(value)
        if fraction is None:
            raise CommandError(
                f"Couldn't read {value!r} as a position. Use a fraction like "
                "1/3 or a decimal like 0.5."
            )
        if not 0.0 <= fraction <= 1.0:
            raise CommandError(
                f"Position must be between 0 and 1 (got {fraction:g})."
            )
        return fraction

    def _as_canvas_fraction(self, argument) -> float:
        """A position down the canvas, allowed to fall outside the frame.

        The scene is much larger than the reference frame, so a figure can be
        built above or below it. ``0`` is still the top of the frame and ``1``
        the bottom; ``-0.5`` and ``1.5`` are half a frame beyond each.

        Args:
            argument: A fraction or decimal, or a form yielding one.

        Returns:
            The value, unclamped.
        """
        value = self._value(argument)
        fraction = parse_fraction(value)
        if fraction is None:
            raise CommandError(
                f"Couldn't read {value!r} as a position. Use a fraction like "
                "1/3 or a decimal like 0.5."
            )
        return fraction

    def _one(self, value, noun: str):
        """One thing from a value that may be a list of one.

        The filters give back lists, so ``(points-off L2 tri)`` yielding a
        single point should compose where a point is wanted. Several is
        ambiguous and says so; none is said plainly too.
        """
        if not isinstance(value, list):
            return value
        if len(value) == 1:
            return value[0]
        if not value:
            raise CommandError(f"That gave no {noun} at all.")
        raise CommandError(
            f"That gave {len(value)} of them — {self._render(value)} — but "
            f"one {noun} is wanted here. Narrow it, e.g. with (take 1 …)."
        )

    def _describe(self, value) -> str:
        """A value as the user would recognise it, never a raw Python repr."""
        if isinstance(value, Lambda):
            return value.name or value.described()
        if isinstance(value, (PointItem, LineItem)):
            return self._element_name(value)
        if isinstance(value, list):
            return self._render(value)
        return repr(value)

    def _as_point(self, argument) -> PointItem:
        value = self._one(self._value(argument), "point")
        if isinstance(value, PointItem):
            return value
        if isinstance(value, str):
            return self.resolve_point(value)
        raise CommandError(f"Expected a point, got {self._describe(value)}.")

    def _as_line(self, argument) -> LineItem:
        value = self._one(self._value(argument), "line")
        if isinstance(value, LineItem):
            return value
        if isinstance(value, str):
            return self.resolve_line(value)
        raise CommandError(f"Expected a line, got {self._describe(value)}.")

    def _as_element(self, argument):
        """Resolve an argument to a point or a line, whichever it names."""
        value = self._one(self._value(argument), "element")
        if isinstance(value, (PointItem, LineItem)):
            return value
        if isinstance(value, str):
            return self.resolve_element(value)
        raise CommandError(
            f"Expected a point or a line, got {self._describe(value)}."
        )

    # -- Element access ----------------------------------------------------

    def _points(self):
        return sorted(
            (it for it in self.scene.items() if isinstance(it, PointItem)),
            key=lambda p: getattr(p, "_seq", 0),
        )

    def _lines(self):
        return sorted(self.scene._lines(), key=lambda ln: getattr(ln, "_seq", 0))

    def resolve_point(self, name: str) -> PointItem:
        """Find a point by label (``A``) or by its ``list`` id (``P1``).

        Crossings count as points here: geometry can be built on them.
        """
        points = self._points()  # same order/numbering as the (ls) command
        match = _match_by_label(points, name) or _match_by_id(points, name, "p")
        if match is None:
            raise CommandError(
                f"No point named {name!r}. Use a label (e.g. A) or an id from "
                "(ls) (e.g. P1)."
            )
        return match

    def resolve_element(self, name: str):
        """Find a point *or* a line by label (``A``, ``a``) or id (``P1``, ``L1``).

        Unlike :meth:`resolve_point`, intersection points resolve here — they
        are real items on the canvas, and it's up to the caller to decide what
        may be done with one.
        """
        points = self._points()
        match = _match_by_label(points, name) or _match_by_id(points, name, "p")
        if match is not None:
            return match
        lines = self._lines()
        match = _match_by_label(lines, name) or _match_by_id(lines, name, "l")
        if match is None:
            raise CommandError(
                f"No element named {name!r}. Use a label (A, a) or an id from "
                "(ls) (P1, L1)."
            )
        return match

    def resolve_line(self, name: str) -> LineItem:
        """Find a line by label (``a``) or by its ``list`` id (``L1``)."""
        lines = self._lines()
        match = _match_by_label(lines, name) or _match_by_id(lines, name, "l")
        if match is None:
            raise CommandError(
                f"No line named {name!r}. Use a label (e.g. a) or an id from "
                "(ls) (e.g. L1)."
            )
        return match

    # -- Forms -------------------------------------------------------------

    def _form_help(self, args) -> str:
        return (
            "Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Forms return the element they make, so they nest:\n"
            "  (add-line 260 (point L1 2/3))\n"
            "\n"
            "  (add point <across> <down>) a point placed on the canvas;\n"
            "                              0 0 = top-left, 1 1 = bottom-right\n"
            "  (add horizon <fraction>)    horizontal, orientation-locked line;\n"
            "                              0 = top of canvas, 1 = bottom;\n"
            "                              outside that is beyond the frame\n"
            "  (add-line <pts> <pts>)      a line from each of the first points\n"
            "                              to each of the second, bound to both;\n"
            "                              one of each is the plain case, as in\n"
            "                              (add-line (list P1) (list P2))\n"
            "  (add-line <angle> <pts>)    a line through each point, at an\n"
            "                              angle in degrees clockwise from\n"
            "                              horizontal; pinned to the point\n"
            "  (point <line> <fraction>)   a point along a line, 0 = its left\n"
            "                              end, 1 = its right; anchored to it\n"
            "  (point <line> <line>)       the point where two lines meet\n"
            "  (rm <element>)              remove a point or line; lines left\n"
            "                              behind simply come free\n"
            "  (clear)                     empty the canvas; defined names and\n"
            "                              functions are kept\n"
            "  (label <element> <text>)    name a point or line; quote text\n"
            "                              with spaces, \"\" removes the label\n"
            "  (format <line> <w> <c> <s>) thickness, colour, dash style\n"
            "  (label -auto)               label everything: points A, B, C…\n"
            "                              and lines a, b, c…\n"
            "  (label -clear)              remove every label\n"
            "  (hide <element>)            stop drawing it; nothing is lost\n"
            "  (show <element> | -all)     draw it again\n"
            "  (draw-triangle <p> <p> <p>) the three sides joining three\n"
            "                              points (or a list of three)\n"
            "  (draw-cevians <tri> <line>) from each crossing on the line,\n"
            "                              an edge to the vertex lacking one\n"
            "  (points) / (lines)          everything on the canvas\n"
            "  (meets <lines>)             where those lines cross\n"
            "  (lines-through <point>)     the lines it lies on\n"
            "  (points-on <line> [<pts>])  those that lie on it\n"
            "  (points-off <line> [<pts>]) those that do not\n"
            "  (join <points>)             a line between every pair\n"
            "  (diff <list> <list>)        what is in the first but not the\n"
            "                              second\n"
            "  (intersect <list> <list>)   what is in both\n"
            "  (take <n> <list>)           the first n of a list\n"
            "  (last <n> <list>)           the last n — what was just made\n"
            "  (repeat <n> <form>)         run a form n times\n"
            "  (list <element> …)          gather elements into a list\n"
            "  (define <name> <value>)     give a value a name\n"
            "  (lambda (<name> …) <body>)  a function, as a value; the names\n"
            "                              are its parameters\n"
            "  (define (<name> <p> …) …)   name a function, the short way;\n"
            "                              then (<name> P1) calls it\n"
            "  (map <function> <list>)     call it on each element in turn\n"
            "  (ls [-points | -lines])     list canvas elements\n"
            "  (help)                      show this help\n"
            "\n"
            "Elements are named by label (A, a) or by id from (ls) (P1, L1)."
        )

    def _form_add(self, args):
        if not args:
            raise CommandError(
                "Usage: (add point <across> <down>) or (add horizon "
                "<fraction>); a line is (add-line …)"
            )
        what = args[0]
        if not isinstance(what, str):
            raise CommandError(
                "Usage: (add point ...) or (add horizon ...); a line is "
                "(add-line ...)"
            )
        what = what.lower()
        if what == "horizon":
            return self._add_horizon(args[1:])
        if what == "point":
            return self._add_point(args[1:])
        if what == "line":
            raise CommandError(
                "(add line …) is now (add-line …), and it takes lists:\n"
                "  (add-line (list P1) (list P2))   the line P1-P2\n"
                "  (add-line 30 (list P1))          at 30 degrees through P1"
            )
        raise CommandError(
            f"Don't know how to add {args[0]!r}. Try (add point <across> "
            "<down>) or (add horizon <fraction>); a line is (add-line …)."
        )

    def _add_point(self, args) -> PointItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (add point <across> <down>)\n"
                "  across: 0 = left edge of canvas, 1 = right edge\n"
                "  down:   0 = top of canvas, 1 = bottom\n"
                "  e.g. (add point 1/3 1/3)"
            )
        across = self._as_canvas_fraction(args[0])
        down = self._as_canvas_fraction(args[1])
        return self.scene.add_point_at(across, down)

    def _add_horizon(self, args) -> LineItem:
        if not args:
            raise CommandError(
                "Usage: (add horizon <fraction>)\n"
                "  0 = top of canvas, 1 = bottom; outside that is above or\n"
                "  below the frame. e.g. (add horizon 1/3)"
            )
        return self.scene.add_horizon(self._as_canvas_fraction(args[0]))

    #: How the form describes itself when it is called wrongly.
    _ADD_LINE_USAGE = (
        "Usage: (add-line <points> <points>)  - each of the first joined\n"
        "                                       to each of the second\n"
        "   or: (add-line <angle> <points>)   - through each point\n"
        "  angle:  degrees clockwise from horizontal (e.g. 30, -45)\n"
        "  points: a label (A), an id (P1), a form like (point L1 2/3), or a\n"
        "          list of them, like (list P1 P2) — one of each draws one line"
    )

    def _form_add_line(self, args):
        """``(add-line (list P1) (list P2 P3))`` — join each of these to each of those.

        Takes lists throughout. One-element lists are the plain case, so
        ``(add-line (list P1) (list P2))`` is the single line P1–P2; given
        longer lists, a line is drawn from every point of the first to every
        point of the second, which is how a net grows a round at a time. A
        pair already joined is reused rather than drawn over.

        The angle form takes a list too: ``(add-line 30 (list P1 P2))`` pins a
        line at 30° through each of those points.

        Returns:
            The line, if one came of it; otherwise the lines, as a list.
        """
        if len(args) != 2:
            raise CommandError(self._ADD_LINE_USAGE)
        first = args[0]
        if isinstance(first, str) and _is_number(first):
            # (add-line <angle> <points>)
            angle = float(first)
            points = self._flatten(args[1:], PointItem, "point")
            if not points:
                raise CommandError("No points to draw a line through.")
            return self._only(
                [self.scene.add_line_through(point, angle) for point in points]
            )
        # (add-line <points> <points>)
        starts = self._flatten([args[0]], PointItem, "point")
        ends = self._flatten([args[1]], PointItem, "point")
        if not starts or not ends:
            raise CommandError("No points to join: one of those lists is empty.")
        pairs = len(starts) * len(ends)
        if pairs > self.JOIN_LIMIT:
            raise CommandError(
                f"That would draw up to {pairs} lines, from {len(starts)} "
                f"points to {len(ends)} (the limit is {self.JOIN_LIMIT}). "
                "Narrow the lists — (take …) or (diff …) — and draw a part "
                "of them."
            )
        drawn = []
        for a in starts:
            for b in ends:
                if a is b or a.center() == b.center():
                    continue
                line = self._join(a, b)
                if not any(other is line for other in drawn):
                    drawn.append(line)
        if not drawn:
            raise CommandError(
                "Can't draw a line: those are the same point, or two points in "
                "the same place."
            )
        return self._only(drawn)

    @staticmethod
    def _only(lines: list):
        """One line on its own, so a single join reads as it always did."""
        return lines[0] if len(lines) == 1 else lines

    def _form_clear(self, args) -> str:
        """``(clear)`` — empty the canvas.

        The names you have defined are **left alone**: a list prunes itself
        to what is still there when it is next used, and a function doesn't
        depend on the canvas at all. So a script can clear and rebuild
        without losing what it defined — which is the usual way to start one,
        since a script otherwise draws on top of whatever is already there.

        Undo brings the canvas back.

        Returns:
            What was cleared.
        """
        if args:
            raise CommandError(
                "(clear) takes nothing — it empties the whole canvas.\n"
                "  To remove one element, use (rm <element>)."
            )
        points, lines = len(self._points()), len(self._lines())
        if not points and not lines:
            return "The canvas is already empty."
        self.scene.clear_all()
        return f"Cleared {_count(points, 'point')} and {_count(lines, 'line')}."

    def _form_point(self, args) -> PointItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (point <line> <fraction>)  a point along a line\n"
                "   or: (point <line> <line>)      where two lines meet\n"
                "  0 = the line's left-hand end, 1 = its right-hand end"
            )
        line = self._as_line(args[0])
        second = self._value(args[1])
        if isinstance(second, LineItem) or (
            isinstance(second, str) and parse_fraction(second) is None
        ):
            return self._meet_of(line, self._as_line(args[1]))
        fraction = self._as_canvas_fraction(args[1])
        point = self.scene.add_point_on_line(line, fraction)
        if point is None:
            raise CommandError("That line doesn't cross the canvas.")
        return point

    def _meet_of(self, a: LineItem, b: LineItem) -> PointItem:
        """The point where two lines meet, shown if it was hidden.

        Nothing is created: a point is already kept wherever lines cross. If
        it was hidden, asking for it is a good enough reason to draw it again.
        """
        if a is b:
            raise CommandError("A line meets itself everywhere.")
        point = self.scene.meet_of(a, b)
        if point is None:
            raise CommandError(
                f"{self._line_name(a)} and {self._line_name(b)} don't meet on "
                "the canvas — they may be parallel, or cross off it."
            )
        if point.set_shown(True):
            self.scene.commit_undo()
        return point

    def _each(self, argument, what):
        """Apply ``what`` to one element or to every element in a list.

        Args:
            argument: An element, or a list of them.
            what: Callable taking one element and returning a line of output.

        Returns:
            The outputs, newline-joined.
        """
        value = self._value(argument)
        if isinstance(value, list):
            if not value:
                raise CommandError("That list is empty.")
            return "\n".join(what(item) for item in value)
        return what(self._as_element(argument))

    def _form_draw_triangle(self, args) -> list:
        """``(draw-triangle P1 P2 P3)`` — the three sides joining three points.

        Takes three points, or a list of three: ``(draw-triangle tri)`` works
        just as well. A side that is already drawn is reused rather than drawn
        again, so triangles sharing an edge don't stack lines on top of each
        other.

        Returns:
            The three sides, as a list.
        """
        points = []
        for argument in args:
            value = self._value(argument)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, str):
                    item = self.resolve_point(item)
                if not isinstance(item, PointItem):
                    raise CommandError(f"Expected a point, got {item!r}.")
                points.append(item)
        if len(points) != 3:
            raise CommandError(
                "Usage: (draw-triangle <point> <point> <point>)\n"
                "   or: (draw-triangle <list of three points>)\n"
                f"  got {len(points)} point(s)."
            )
        for index, point in enumerate(points):
            if any(other is point for other in points[index + 1:]):
                raise CommandError(
                    "A triangle needs three distinct points; that is the same "
                    "point twice."
                )
        if self._collinear(*points):
            raise CommandError(
                "Those three points are collinear, so they bound no triangle "
                "— all three sides would be the same line."
            )
        sides = [
            self._join(points[first], points[second])
            for first, second in ((0, 1), (1, 2), (2, 0))
        ]
        return sides

    def _form_draw_cevians(self, args) -> list:
        """``(draw-cevians tri L1)`` — a cevian for each crossing on a line.

        Each side of the triangle meets the given line somewhere, and that
        meeting point is already joined to the two vertices of its own side.
        The third vertex is the one with no edge to it; this draws that edge,
        for each of the three crossings.

        Returns:
            The three cevians, as a list.
        """
        if len(args) < 2:
            raise CommandError(
                "Usage: (draw-cevians <point> <point> <point> <line>)\n"
                "   or: (draw-cevians <triangle> <line>)"
            )
        across = self._as_line(args[-1])
        corners = self._flatten(args[:-1], PointItem, "point")
        if len(corners) != 3:
            raise CommandError(
                f"A triangle is three points; got {len(corners)}."
            )
        drawn = []
        for index in range(3):
            first, second = corners[index], corners[(index + 1) % 3]
            apex = corners[(index + 2) % 3]
            side = self._existing_side(first, second)
            if side is None:
                raise CommandError(
                    f"{self._point_name(first)} and {self._point_name(second)} "
                    "aren't joined — draw the triangle first."
                )
            crossing = self.scene.meet_of(side, across)
            if crossing is None:
                raise CommandError(
                    f"{self._line_name(side)} doesn't meet "
                    f"{self._line_name(across)} on the canvas, so there is no "
                    "point there to draw to."
                )
            drawn.append(self._join(apex, crossing))
        return drawn

    @staticmethod
    def _collinear(a: PointItem, b: PointItem, c: PointItem) -> bool:
        """Whether three points lie on one line."""
        first, second, third = a.center(), b.center(), c.center()
        cross = (second.x() - first.x()) * (third.y() - first.y()) - (
            second.y() - first.y()
        ) * (third.x() - first.x())
        return abs(cross) < 1e-6

    def _existing_side(self, a: PointItem, b: PointItem):
        """The line the figure already has through both points, if any.

        Two distinct points determine one line, so if the figure already says
        both of these lie on a line, that line *is* their join and there is
        nothing to draw. The test is the dual of
        :meth:`_form_lines_through`, and asks the same recorded-relation
        question: a crossing on a side is on that side, so joining it to
        either end of that side asks for the side itself.

        A line bound to both points is preferred, so a side drawn as a side
        comes back ahead of one the two merely happen to share.
        """
        through = self.scene.lines_through
        shared = [
            line
            for line in through(a)
            if any(other is line for other in through(b))
        ]
        pair = {id(a), id(b)}
        for line in shared:
            ends = {
                id(line.bound_point(end))
                for end in (1, 2)
                if line.bound_point(end) is not None
            }
            if ends == pair:
                return line
        return shared[0] if shared else None

    def _join(self, a: PointItem, b: PointItem) -> LineItem:
        """The line joining two points, drawn only if it isn't there already."""
        existing = self._existing_side(a, b)
        if existing is not None:
            return existing
        line = self.scene.add_line_between(a, b)
        if line is None:
            raise CommandError(
                "Can't draw a side: two of those points are in the same place."
            )
        return line

    # -- Enumerators -------------------------------------------------------

    #: Most sides one (join …) will draw before refusing. Joining n points
    #: pairwise is n(n-1)/2 lines, which runs away fast: 20 points is 190.
    JOIN_LIMIT = 300

    #: Most times (repeat …) will run a form.
    REPEAT_LIMIT = 100

    def _form_points(self, args) -> list:
        """``(points)`` — every point on the canvas, as a list."""
        if args:
            raise CommandError("(points) takes nothing.")
        return list(self._points())

    def _form_lines(self, args) -> list:
        """``(lines)`` — every line on the canvas, as a list."""
        if args:
            raise CommandError("(lines) takes nothing.")
        return list(self._lines())

    def _form_meets(self, args) -> list:
        """``(meets <lines>)`` — the points where those lines cross."""
        lines = self._flatten(args, LineItem, "line")
        wanted = {id(line) for line in lines}
        return [
            point
            for point in self._points()
            if point.is_meet()
            and sum(1 for ln in point.meeting_lines() if id(ln) in wanted) >= 2
        ]

    def _form_lines_through(self, args) -> list:
        """``(lines-through P1)`` — the lines that point lies on.

        A list of points may be given, in which case the lines through any of
        them come back, each once.
        """
        points = self._flatten(args, PointItem, "point")
        if not points:
            raise CommandError("Usage: (lines-through <point>)")
        found = []
        for point in points:
            for line in self.scene.lines_through(point):
                if not any(other is line for other in found):
                    found.append(line)
        return found

    def _form_points_on(self, args) -> list:
        """``(points-on L1 <points>)`` — those of them that lie on the line.

        With no list, every point on the line. The dual of
        :meth:`_form_lines_through`, and it asks the same question: the figure
        has to *say* the point is on the line — it is the line's crossing, or
        bound, pinned or anchored to it.
        """
        return self._by_incidence(args, "points-on", on=True)

    def _form_points_off(self, args) -> list:
        """``(points-off L1 <points>)`` — those of them that do not."""
        return self._by_incidence(args, "points-off", on=False)

    def _by_incidence(self, args, form: str, on: bool) -> list:
        if not args:
            raise CommandError(f"Usage: ({form} <line> [<points>])")
        line = self._as_line(args[0])
        candidates = (
            self._flatten(args[1:], PointItem, "point")
            if len(args) > 1
            else list(self._points())
        )
        through = self.scene.lines_through
        return [
            point
            for point in candidates
            if any(other is line for other in through(point)) == on
        ]

    def _form_join(self, args) -> list:
        """``(join <points>)`` — a line between every pair of them.

        The sides a net is made of. A pair the figure already has a line
        through is left alone rather than drawn over, so joining overlapping
        sets doesn't stack lines, and each line comes back once however many
        pairs it answered for.
        """
        points = self._flatten(args, PointItem, "point")
        if len(points) < 2:
            raise CommandError("(join …) needs at least two points.")
        pairs = len(points) * (len(points) - 1) // 2
        if pairs > self.JOIN_LIMIT:
            raise CommandError(
                f"That would draw {pairs} lines from {len(points)} points "
                f"(the limit is {self.JOIN_LIMIT}). Narrow the list — (take …) "
                "or (diff …) — and join a part of it."
            )
        drawn = []
        for first in range(len(points)):
            for second in range(first + 1, len(points)):
                a, b = points[first], points[second]
                if a is b or a.center() == b.center():
                    continue
                line = self._join(a, b)
                if not any(other is line for other in drawn):
                    drawn.append(line)
        return drawn

    def _form_diff(self, args) -> list:
        """``(diff <list> <list>)`` — what is in the first but not the second.

        Set difference, and the exact counterpart of
        :meth:`_form_intersect`: this drops the elements the second list has,
        where that one keeps them. Between them they divide the first list in
        two, in its own order.

        Elements are matched by **identity**, not by looking alike — two
        points in the same place are two points.

        Returns:
            What is left, in the order the first list had it.
        """
        if len(args) != 2:
            raise CommandError(
                "Usage: (diff <list> <list>)\n"
                "  e.g. (diff (points) (points-on L1))"
            )
        keep = self._as_list(args[0])
        drop = {id(item) for item in self._as_list(args[1])}
        return [item for item in keep if id(item) not in drop]

    def _form_without_moved(self, args):
        """``(without …)`` was renamed, to sit with the other set forms."""
        raise CommandError(
            "(without …) is now (diff …), to go with (intersect …):\n"
            "  (diff a b)   what is in a but not in b"
        )

    def _form_intersect(self, args) -> list:
        """``(intersect <list> <list>)`` — what is in both.

        The exact counterpart of :meth:`_form_diff`: it keeps the elements
        of the first list that appear in the second, where that one drops
        them. Between them they divide the first list in two, in its own
        order, so ``(list (intersect a b) (diff a b))`` is ``a`` again.

        Elements are matched by **identity**, not by looking alike — two
        points in the same place are two points.

        Returns:
            The shared elements, in the order the first list had them.
        """
        if len(args) != 2:
            raise CommandError(
                "Usage: (intersect <list> <list>)\n"
                "  e.g. (intersect (points-on L1) (points-on L2))"
            )
        keep = self._as_list(args[0])
        shared = {id(item) for item in self._as_list(args[1])}
        return [item for item in keep if id(item) in shared]

    def _form_take(self, args) -> list:
        """``(take <n> <list>)`` — the first n of a list."""
        if len(args) != 2:
            raise CommandError("Usage: (take <count> <list>)")
        count = int(self._as_float(args[0], "a count"))
        return self._as_list(args[1])[:max(0, count)]

    def _form_last(self, args) -> list:
        """``(last <n> <list>)`` — the last n of a list.

        Points come in creation order, so the last of them are the ones the
        step before just made. That is how a net reaches forward instead of
        re-joining the seed it started from.
        """
        if len(args) != 2:
            raise CommandError("Usage: (last <count> <list>)")
        count = int(self._as_float(args[0], "a count"))
        items = self._as_list(args[1])
        return items[-count:] if count > 0 else []

    def _form_repeat(self, args):
        """``(repeat <n> <form>)`` — run a form n times.

        The form is re-evaluated each round, so anything reading the canvas —
        ``(points)``, ``(lines)`` — sees what the round before it made. That
        is how a net grows without naming each generation.
        """
        if len(args) != 2:
            raise CommandError("Usage: (repeat <count> <form>)")
        count = int(self._as_float(args[0], "a count"))
        if count < 0 or count > self.REPEAT_LIMIT:
            raise CommandError(
                f"Repeat between 0 and {self.REPEAT_LIMIT} times."
            )
        result = None
        for _ in range(count):
            result = self._value(args[1])
        return result

    def _as_list(self, argument) -> list:
        """An argument as a list, whether it is one or a single element."""
        value = self._value(argument)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            value = self._as_element(argument)
        return [value]

    def _flatten(self, args, kind, noun: str) -> list:
        """Every element across the arguments, checked to be of one kind."""
        found = []
        for argument in args:
            for item in self._as_list(argument):
                if not isinstance(item, kind):
                    raise CommandError(
                        f"Expected a {noun}, got {self._element_name(item)}."
                    )
                if not any(other is item for other in found):
                    found.append(item)
        return found

    def _form_rm(self, args) -> str:
        if len(args) != 1:
            raise CommandError(
                "Usage: (rm <element>)\n"
                "  element: a label (A, a) or an id from (ls) (P1, L1)\n"
                "  e.g. (rm P1)"
            )
        value = self._value(args[0])
        if isinstance(value, list):
            if not value:
                raise CommandError("That list is empty.")
            # Names are positional, so read them all before removing any:
            # otherwise every line of the output says P1.
            described = [self._render(item) for item in value]
            return "\n".join(
                self._remove_one(item, text)
                for item, text in zip(value, described)
            )
        return self._remove_one(self._as_element(args[0]))

    def _remove_one(self, element, described: str | None = None) -> str:
        if described is None:
            described = self._render(element)
        if isinstance(element, PointItem) and element.is_meet():
            # The lines still meet there, so the point can't be removed — but
            # it can be put out of the way, which is what was meant.
            element.set_shown(False)
            self.scene.commit_undo()
            return (
                f"Hid {described}\n"
                "  (the lines still cross there; (show -all) brings it back)"
            )
        self.scene.remove_element(element)
        return f"Removed {described}"

    def _form_label(self, args):
        if not args:
            raise CommandError(_LABEL_USAGE)
        first = args[0]
        if isinstance(first, str) and first.startswith("-"):
            if len(args) != 1:
                raise CommandError(f"{first} takes nothing else.")
            key = first.lstrip("-").lower()
            if key == "auto":
                points, lines = self.scene.auto_label()
                return (
                    f"Labelled {_count(points, 'point')} "
                    f"and {_count(lines, 'line')}."
                )
            if key == "clear":
                return f"Cleared {_count(self.scene.clear_labels(), 'label')}."
            raise CommandError(
                f"Unknown qualifier: {first!r}. Use -auto or -clear."
            )
        if len(args) != 2:
            raise CommandError(_LABEL_USAGE)
        text = str(self._value(args[1]))
        value = self._value(args[0])
        if isinstance(value, list):
            # One name would be ambiguous across several elements, so each
            # gets the text with its position appended: A1, A2, A3.
            for index, element in enumerate(value, 1):
                self.scene.label_element(element, f"{text}{index}")
            return self._render(value)
        element = self._as_element(args[0])
        self.scene.label_element(element, text)
        return element

    #: Dash styles a line can be given, as ``(format …)`` names them.
    LINE_STYLES = {
        "solid": Qt.SolidLine,
        "dashed": Qt.DashLine,
        "dotted": Qt.DotLine,
        "dash-dot": Qt.DashDotLine,
        "dash-dot-dot": Qt.DashDotDotLine,
    }

    def _form_format(self, args) -> str:
        """``(format L1 0.5 #d3d3d3 "dashed")`` — how a line is drawn.

        Thickness, colour and style, in that order; any of them may be left
        off, and a list of lines may be given instead of one.
        """
        if not 2 <= len(args) <= 4:
            raise CommandError(_FORMAT_USAGE)
        width = self._as_float(args[1], "a thickness") if len(args) > 1 else None
        color = self._as_color(args[2]) if len(args) > 2 else None
        style = self._as_line_style(args[3]) if len(args) > 3 else None

        lines = self._flatten([args[0]], LineItem, "line")
        if not lines:
            raise CommandError("(format …) needs a line to work on.")
        for line in lines:
            line.set_style(color=color, width=width, style=style)
        self.scene.commit_undo()
        described = ", ".join(self._line_name(line) for line in lines)
        return f"Formatted {described}"

    def _as_color(self, argument) -> QColor:
        """Read a colour: ``#rrggbb``, or a name Qt knows."""
        value = str(self._value(argument))
        color = QColor(value)
        if not color.isValid():
            raise CommandError(
                f"Couldn't read {value!r} as a colour. Use a hex code like "
                "#d3d3d3, or a name like grey."
            )
        return color

    def _as_line_style(self, argument):
        """Read a dash style by name."""
        value = str(self._value(argument)).strip().lower()
        style = self.LINE_STYLES.get(value)
        if style is None:
            raise CommandError(
                f"Unknown line style {value!r}. Use one of: "
                + ", ".join(sorted(self.LINE_STYLES))
            )
        return style

    def _form_hide(self, args) -> str:
        if len(args) != 1:
            raise CommandError("Usage: (hide <element>)  e.g. (hide P3)")
        return self._each(args[0], self._hide_one)

    def _hide_one(self, element) -> str:
        described = self._render(element)
        if not element.set_shown(False):
            return f"{described} was already hidden."
        self.scene.commit_undo()
        return f"Hid {described}"

    def _form_show(self, args) -> str:
        if len(args) != 1:
            raise CommandError(
                "Usage: (show <element>) or (show -all)  e.g. (show P3)"
            )
        first = args[0]
        if isinstance(first, str) and first.lstrip("-").lower() == "all":
            return f"Showed {_count(self.scene.show_all_points(), 'point')}."
        return self._each(first, self._show_one)

    def _show_one(self, element) -> str:
        if not element.set_shown(True):
            return f"{self._render(element)} was already showing."
        self.scene.commit_undo()
        return f"Showing {self._render(element)}"  # described as it now is

    def _form_list(self, args) -> list:
        """``(list P1 P2 L1)`` — gather elements into a list value."""
        if not args:
            raise CommandError(
                "(list …) gathers elements, e.g. (list P1 P2 P3).\n"
                "  To see what's on the canvas, use (ls)."
            )
        gathered = []
        for argument in args:
            value = self._value(argument)
            if isinstance(value, str) and value.lstrip("-").lower() in (
                "points", "point", "p", "lines", "line", "l"
            ):
                raise CommandError(
                    f"(list …) gathers elements now; use (ls {value}) to see "
                    "what's on the canvas."
                )
            if isinstance(value, list):
                gathered.extend(value)  # lists flatten, so they compose
            else:
                gathered.append(self._as_element(argument))
        return gathered

    def _form_define(self, args) -> str:
        """``(define tri (list P1 P2 P3))`` — give a value a name.

        A function may be written the short way, with the name and its
        parameters together::

            (define (cevian q) (add-line (list q) (points-off L1 tri)))

        which is the same as naming a :meth:`_form_lambda`.
        """
        if args and isinstance(args[0], list):
            return self._define_function(args)
        if len(args) != 2:
            raise CommandError(
                "Usage: (define <name> <value>)\n"
                "   or: (define (<name> <param> …) <body>)   a function\n"
                "  e.g. (define tri (list P1 P2 P3))"
            )
        name = args[0]
        if not isinstance(name, str):
            raise CommandError("A name must be a bare word, e.g. (define tri …).")
        if parse_fraction(name) is not None:
            raise CommandError(f"{name!r} is a number, not a name.")
        value = self._value(args[1])
        if isinstance(value, Lambda):
            value.name = name
        elif isinstance(value, str):
            value = self._as_element(args[1])
        self._variables[name] = value
        return f"{name} = {self._render(value)}"

    def _define_function(self, args) -> str:
        """``(define (cevian q) <body>)`` — a named function, the short way."""
        if not args[0]:
            raise CommandError(
                "That gives the function no name, e.g. (define (cevian q) …)."
            )
        name, params = args[0][0], args[0][1:]
        if not isinstance(name, str):
            raise CommandError(
                "A name must be a bare word, e.g. (define (cevian q) …)."
            )
        if parse_fraction(name) is not None:
            raise CommandError(f"{name!r} is a number, not a name.")
        function = self._form_lambda([list(params)] + list(args[1:]))
        function.name = name
        self._variables[name] = function
        return f"{name} = {self._render(function)}"

    #: How deep calls may nest, so a function that calls itself for ever
    #: says so rather than dying inside Python.
    CALL_LIMIT = 50

    def _form_lambda(self, args) -> Lambda:
        """``(lambda (q) <body>)`` — a function, as a value.

        The parameters are bare words in a list; the body is one or more
        forms, run in order with the parameters bound, and the last one's
        value is the function's value. Nothing is evaluated until it is
        called.

        Give it a name with :meth:`_form_define` and it reads as a command of
        its own::

            (define cevian (lambda (q) (add-line (list q) (points-off L1 tri))))
            (cevian P4)

        Returns:
            The function.
        """
        if len(args) < 2:
            raise CommandError(
                "Usage: (lambda (<name> …) <body>)\n"
                "  e.g. (lambda (q) (add-line (list q) (points-off L1 tri)))\n"
                "  The names are the parameters; the body runs when the\n"
                "  function is called."
            )
        params = args[0]
        if not isinstance(params, list):
            raise CommandError(
                "A lambda's parameters go in their own parentheses, e.g. "
                "(lambda (q) …) — one name per argument."
            )
        for param in params:
            if not isinstance(param, str):
                raise CommandError(
                    "A parameter must be a bare word, e.g. (lambda (q) …)."
                )
            if parse_fraction(param) is not None:
                raise CommandError(f"{param!r} is a number, not a name.")
            if params.count(param) > 1:
                raise CommandError(f"{param!r} is named twice in one lambda.")
        return Lambda(list(params), list(args[1:]), list(self._scope))

    def _apply(self, callee, args, named: str):
        """Call a function (or a one-argument form) on arguments already read.

        Args:
            callee: A :class:`Lambda`, or the name of a built-in form.
            args: The arguments, which may be values or raw s-expressions.
            named: What to call the callee in a message.

        Returns:
            The body's last value.
        """
        if isinstance(callee, str) and callee.lower() in self._forms:
            # (map hide …) — any one-argument form can be mapped too.
            return self._forms[callee.lower()](list(args))
        if not isinstance(callee, Lambda):
            raise CommandError(
                f"{named} isn't a function, so it can't be called — it is "
                f"{self._describe(callee)}."
            )
        if len(args) != len(callee.params):
            wanted = " ".join(callee.params) or "nothing"
            raise CommandError(
                f"{callee.name or named} takes {len(callee.params)} "
                f"argument(s) ({wanted}), but got {len(args)}."
            )
        if self._depth >= self.CALL_LIMIT:
            raise CommandError(
                f"Calls are nested more than {self.CALL_LIMIT} deep — a "
                "function is probably calling itself without end."
            )
        frame = {
            param: self._value(argument)
            for param, argument in zip(callee.params, args)
        }
        saved = self._scope
        # The scope it was written in, not the one calling it.
        self._scope = list(callee.scope) + [frame]
        self._depth += 1
        try:
            value = None
            for form in callee.body:
                value = self._value(form)
            return value
        finally:
            self._depth -= 1
            self._scope = saved

    def _form_map(self, args) -> list:
        """``(map <function> <list>)`` — call it on each element in turn.

        The lispy way to do a thing once per element, where the thing depends
        on the element. The function may be a lambda, the name of one, or the
        name of a form taking a single argument::

            (map (lambda (q) (add-line (list q) (points-off L1 tri)))
                 (points-on L1))
            (map hide (points-on L1))

        Results are gathered into one **flat** list, as lists are everywhere
        else in the language, so a function drawing several lines per element
        still gives back a list of lines.

        Returns:
            What the calls gave, flattened.
        """
        if len(args) != 2:
            raise CommandError(
                "Usage: (map <function> <list>)\n"
                "  e.g. (map (lambda (q) (add-line (list q) tri)) (points-on L1))\n"
                "  The function takes one argument: each element in turn."
            )
        callee = self._value(args[0])
        items = self._as_list(args[1])
        if not items:
            raise CommandError("That list is empty, so there is nothing to map.")
        gathered = []
        for item in items:
            value = self._apply(callee, [item], self._describe(callee))
            for result in value if isinstance(value, list) else [value]:
                if result is not None:
                    gathered.append(result)
        if gathered and all(isinstance(item, str) for item in gathered):
            # A form like (hide …) answers with a message, not an element.
            return "\n".join(gathered)
        return gathered

    def _form_ls(self, args) -> str:
        show_points = show_lines = True
        if args:
            show_points = show_lines = False
            for arg in args:
                key = str(arg).lower().lstrip("-")
                if key in ("points", "point", "p"):
                    show_points = True
                elif key in ("lines", "line", "l"):
                    show_lines = True
                else:
                    raise CommandError(
                        f"Unknown qualifier: {arg!r}. Use -points or -lines."
                    )
        blocks = []
        if show_points:
            blocks.append(self._list_points())
        if show_lines:
            blocks.append(self._list_lines())
        return "\n".join(blocks)

    # -- Rendering ---------------------------------------------------------

    def _render(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            inner = " ".join(self._element_name(item) for item in value)
            return f"({inner})"
        if isinstance(value, str):
            return value
        if isinstance(value, Lambda):
            return value.described()
        if isinstance(value, PointItem):
            return f"{self._point_name(value)}  {self._describe_point(value)}"
        if isinstance(value, LineItem):
            return f"{self._line_name(value)}  {self._describe_line(value)}"
        return str(value)

    def _element_name(self, item) -> str:
        """``P1``/``L1`` for an element, or the rendering of anything else."""
        if isinstance(item, PointItem):
            return self._point_name(item)
        if isinstance(item, LineItem):
            return self._line_name(item)
        if isinstance(item, Lambda):
            return item.name or item.described()
        return str(item)

    def _point_name(self, point) -> str:
        points = self._points()
        return f"P{points.index(point) + 1}" if point in points else "P?"

    def _line_name(self, line) -> str:
        lines = self._lines()
        return f"L{lines.index(line) + 1}" if line in lines else "L?"

    def _describe_point(self, point) -> str:
        c = point.center()
        label = f'  "{point.label_text()}"' if point.label_text() else ""
        if point.is_meet():
            names = ", ".join(
                sorted(self._line_name(ln) for ln in point.meeting_lines())
            )
            tag = f"  [meet of {names}]"
        elif point.has_anchor():
            tag = "  [on-line]"
        else:
            tag = ""
        if not point.is_shown():
            tag += "  [hidden]"
        return f"({c.x():.1f}, {c.y():.1f}){label}{tag}"

    def _list_points(self) -> str:
        points = self._points()
        rows = [f"Points ({len(points)}):"]
        for i, point in enumerate(points, 1):
            rows.append(f"  P{i}  {self._describe_point(point)}")
        if not points:
            rows.append("  (none)")
        return "\n".join(rows)

    def _list_lines(self) -> str:
        items = self._lines()
        rows = [f"Lines ({len(items)}):"]
        for i, line in enumerate(items, 1):
            rows.append(f"  L{i}  {self._describe_line(line)}")
        if not items:
            rows.append("  (none)")
        return "\n".join(rows)

    def _describe_line(self, ln: LineItem) -> str:
        seg = ln.scene_line()
        p1, p2 = seg.p1(), seg.p2()
        base = f"({p1.x():.1f}, {p1.y():.1f})->({p2.x():.1f}, {p2.y():.1f})"
        if ln.has_visible_range():
            extent = f"range[-{ln._range_neg:.0f}, +{ln._range_pos:.0f}]"
        else:
            extent = "infinite"
        parts = [base, extent]
        if ln.is_orientation_locked():
            parts.append("locked")
        if ln.has_pivot():
            parts.append("pivot")
        if ln.label_text():
            parts.append(f'"{ln.label_text()}"')
        return "  ".join(parts)


#: Shown whenever (label ...) is called with arguments it can't read.
_LABEL_USAGE = (
    "Usage: (label <element> <text>)   name a point or line\n"
    "   or: (label -auto)              label points A, B, C… and lines a, b, c…\n"
    "   or: (label -clear)             remove every label\n"
    '  e.g. (label P1 A) or (label L1 "the horizon")'
)


def _count(n: int, noun: str) -> str:
    """``3 points`` / ``1 point`` / ``no points``."""
    if n == 0:
        return f"no {noun}s"
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


#: Shown when (format …) can't read its arguments.
_FORMAT_USAGE = (
    "Usage: (format <line> <thickness> [<colour>] [<style>])\n"
    '  e.g. (format L14 0.5 #d3d3d3 "dashed")\n'
    "  colour: a hex code or a name; style: solid, dashed, dotted,\n"
    "  dash-dot, dash-dot-dot. A list of lines works too."
)


def _on_canvas(item) -> bool:
    """Whether an element is still a live item in a scene.

    ``isValid`` first: once Qt has destroyed the C++ object, touching the
    wrapper at all is an error (or worse).
    """
    return (
        item is not None
        and shiboken6.isValid(item)
        and item.scene() is not None
    )


def _match_by_label(items, name: str):
    for item in items:
        if item.label_text() == name:
            return item
    lowered = name.lower()
    for item in items:
        if item.label_text().lower() == lowered:
            return item
    return None


def _count(number: int, noun: str) -> str:
    """``3 points``, but ``1 point``."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _match_by_id(items, name: str, prefix: str):
    if name[:1].lower() != prefix or not name[1:].isdigit():
        return None
    index = int(name[1:])
    return items[index - 1] if 1 <= index <= len(items) else None
