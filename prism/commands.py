"""Command interpreter for the canvas console.

Commands are S-expressions, so they compose: a form's value can be fed
straight into another form.

    (add horizon 1/3)
    (add line 260 P1)
    (add line 260 (point L1 2/3))

Atoms are passed to each form as raw text and interpreted by that form (an
angle, a fraction, an element name); nested forms are evaluated first and yield
real elements. Forms return the element they create, which is what allows the
nesting above.
"""

from prism.items import LineItem, PointItem
from prism.sexpr import SexprError, parse


class CommandError(Exception):
    """A problem the user should see, phrased for them."""


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
        self._forms = {
            "add": self._form_add,
            "point": self._form_point,
            "list": self._form_list,
            "help": self._form_help,
        }

    # -- Entry point -------------------------------------------------------

    #: Forms that only inspect; they aren't worth recording into a script.
    NON_RECORDING = {"list", "help"}

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
        if not isinstance(head, str):
            raise CommandError("A form must start with a command name.")
        form = self._forms.get(head.lower())
        if form is None:
            raise CommandError(f"Unknown command: {head!r}. Type (help).")
        return form(expression[1:])

    def _value(self, argument):
        """Evaluate an argument: nested forms run, atoms pass through as text."""
        if isinstance(argument, list):
            return self._eval(argument)
        return argument

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

    def _as_point(self, argument) -> PointItem:
        value = self._value(argument)
        if isinstance(value, PointItem):
            if value.is_derived:
                raise CommandError(
                    "That is an intersection point. Those are recomputed as "
                    "lines move, so they can't anchor a new line."
                )
            return value
        if isinstance(value, str):
            return self.resolve_point(value)
        raise CommandError(f"Expected a point, got {value!r}.")

    def _as_line(self, argument) -> LineItem:
        value = self._value(argument)
        if isinstance(value, LineItem):
            return value
        if isinstance(value, str):
            return self.resolve_line(value)
        raise CommandError(f"Expected a line, got {value!r}.")

    # -- Element access ----------------------------------------------------

    def _points(self):
        items = [it for it in self.scene.items() if isinstance(it, PointItem)]
        user = sorted(
            (p for p in items if not p.is_derived),
            key=lambda p: getattr(p, "_seq", 0),
        )
        derived = [p for p in items if p.is_derived]
        return user + derived

    def _lines(self):
        return sorted(self.scene._lines(), key=lambda ln: getattr(ln, "_seq", 0))

    def resolve_point(self, name: str) -> PointItem:
        """Find a point by label (``A``) or by its ``list`` id (``P1``)."""
        points = self._points()  # same order/numbering as the (list) command
        match = _match_by_label(points, name) or _match_by_id(points, name, "p")
        if match is None:
            raise CommandError(
                f"No point named {name!r}. Use a label (e.g. A) or an id from "
                "(list) (e.g. P1)."
            )
        if match.is_derived:
            raise CommandError(
                f"{name!r} is an intersection point. Those are recomputed as "
                "lines move, so they can't anchor a new line."
            )
        return match

    def resolve_line(self, name: str) -> LineItem:
        """Find a line by label (``a``) or by its ``list`` id (``L1``)."""
        lines = self._lines()
        match = _match_by_label(lines, name) or _match_by_id(lines, name, "l")
        if match is None:
            raise CommandError(
                f"No line named {name!r}. Use a label (e.g. a) or an id from "
                "(list) (e.g. L1)."
            )
        return match

    # -- Forms -------------------------------------------------------------

    def _form_help(self, args) -> str:
        return (
            "Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Forms return the element they make, so they nest:\n"
            "  (add line 260 (point L1 2/3))\n"
            "\n"
            "  (add horizon <fraction>)    horizontal, orientation-locked line;\n"
            "                              0 = top of canvas, 1 = bottom\n"
            "  (add line <angle> <point>)  line through a point, at an angle in\n"
            "                              degrees clockwise from horizontal;\n"
            "                              pinned to the point\n"
            "  (point <line> <fraction>)   a point along a line, 0 = its left\n"
            "                              end, 1 = its right; anchored to it\n"
            "  (list [-points | -lines])   list canvas elements\n"
            "  (help)                      show this help\n"
            "\n"
            "Elements are named by label (A, a) or by id from (list) (P1, L1)."
        )

    def _form_add(self, args):
        if not args:
            raise CommandError(
                "Usage: (add horizon <fraction>) or (add line <angle> <point>)"
            )
        what = args[0]
        if not isinstance(what, str):
            raise CommandError("Usage: (add horizon ...) or (add line ...)")
        what = what.lower()
        if what == "horizon":
            return self._add_horizon(args[1:])
        if what == "line":
            return self._add_line(args[1:])
        raise CommandError(
            f"Don't know how to add {args[0]!r}. "
            "Try (add horizon <fraction>) or (add line <angle> <point>)."
        )

    def _add_horizon(self, args) -> LineItem:
        if not args:
            raise CommandError(
                "Usage: (add horizon <fraction>)\n"
                "  0 = top of canvas, 1 = bottom. e.g. (add horizon 1/3)"
            )
        return self.scene.add_horizon(self._as_fraction(args[0]))

    def _add_line(self, args) -> LineItem:
        if len(args) < 2:
            raise CommandError(
                "Usage: (add line <angle> <point>)\n"
                "  angle: degrees clockwise from horizontal (e.g. 30, -45)\n"
                "  point: a label (A), an id (P1), or a form like "
                "(point L1 2/3)"
            )
        angle = self._as_float(args[0], "an angle in degrees")
        point = self._as_point(args[1])
        return self.scene.add_line_through(point, angle)

    def _form_point(self, args) -> PointItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (point <line> <fraction>)\n"
                "  0 = the line's left-hand end, 1 = its right-hand end"
            )
        line = self._as_line(args[0])
        fraction = self._as_fraction(args[1])
        point = self.scene.add_point_on_line(line, fraction)
        if point is None:
            raise CommandError("That line doesn't cross the canvas.")
        return point

    def _form_list(self, args) -> str:
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
        if isinstance(value, str):
            return value
        if isinstance(value, PointItem):
            return f"{self._point_name(value)}  {self._describe_point(value)}"
        if isinstance(value, LineItem):
            return f"{self._line_name(value)}  {self._describe_line(value)}"
        return str(value)

    def _point_name(self, point) -> str:
        points = self._points()
        return f"P{points.index(point) + 1}" if point in points else "P?"

    def _line_name(self, line) -> str:
        lines = self._lines()
        return f"L{lines.index(line) + 1}" if line in lines else "L?"

    def _describe_point(self, point) -> str:
        c = point.center()
        label = f'  "{point.label_text()}"' if point.label_text() else ""
        kind = "  [intersection]" if point.is_derived else ""
        anchored = "  on-line" if point.has_anchor_line() else ""
        return f"({c.x():.1f}, {c.y():.1f}){label}{anchored}{kind}"

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


def _match_by_label(items, name: str):
    for item in items:
        if item.label_text() == name:
            return item
    lowered = name.lower()
    for item in items:
        if item.label_text().lower() == lowered:
            return item
    return None


def _match_by_id(items, name: str, prefix: str):
    if name[:1].lower() != prefix or not name[1:].isdigit():
        return None
    index = int(name[1:])
    return items[index - 1] if 1 <= index <= len(items) else None
