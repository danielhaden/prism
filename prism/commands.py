"""Command interpreter for the canvas console — a small Lisp.

Commands are S-expressions, evaluated against an environment:

    (add horizon 1/3)
    (define A (add point 1/3 1/3))
    (add line 30 A)                 ; A is a binding
    (add line 260 (point 'L1 2/3))  ; 'L1 quotes an element id

Evaluation rules:

* numbers (``260``, ``2/3``, ``0.5``) and string literals evaluate to themselves;
* a bare symbol is looked up in the environment (``define`` / ``let`` bindings) —
  an unbound symbol is an error;
* ``'x`` (``quote``) yields the symbol itself; the construction forms resolve a
  quoted symbol to the canvas element with that id or label (``'L1``, ``'A``);
* a form is dispatched on its head; construction forms return the element they
  make, so forms nest.
"""

from prism.items import LineItem, PointItem
from prism.sexpr import SexprError, Symbol, parse


class CommandError(Exception):
    """A problem the user should see, phrased for them."""


class Environment:
    """A scope: a name→value map chained to an optional parent scope."""

    def __init__(self, parent=None):
        self._values = {}
        self.parent = parent

    def define(self, name: str, value) -> None:
        self._values[name] = value

    def lookup(self, name: str):
        scope = self
        while scope is not None:
            if name in scope._values:
                return scope._values[name]
            scope = scope.parent
        raise CommandError(
            f"Unbound name: {name!r}. Define it first with (define {name} …), "
            f"or quote an element id like '{name} to reference it."
        )


class CommandInterpreter:
    def __init__(self, scene):
        self.scene = scene
        #: Top-level scope; bindings persist for the console session.
        self.env = Environment()
        self._special = {
            "quote": self._form_quote,
            "define": self._form_define,
            "let": self._form_let,
            "add": self._form_add,
            "point": self._form_point,
            "list": self._form_list,
            "help": self._form_help,
        }

    # -- Entry point -------------------------------------------------------

    #: Forms that only inspect; they aren't worth recording into a script.
    NON_RECORDING = {"list", "help"}

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
                value = self._eval(expression, self.env)
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
                and isinstance(expression[0], Symbol)
                and expression[0].name.lower() not in self.NON_RECORDING
            ):
                return True
        return False

    # -- Evaluation --------------------------------------------------------

    def _eval(self, expression, env: Environment):
        if isinstance(expression, Symbol):
            return env.lookup(expression.name)
        if isinstance(expression, list):
            if not expression:
                raise CommandError("Empty form ().")
            head = expression[0]
            if not isinstance(head, Symbol):
                raise CommandError("A form must start with a command name.")
            form = self._special.get(head.name.lower())
            if form is None:
                raise CommandError(
                    f"Unknown command: {head.name!r}. Type (help)."
                )
            return form(expression[1:], env)
        # Numbers and string literals evaluate to themselves.
        return expression

    # -- Argument coercion -------------------------------------------------
    #
    # Coercions receive already-evaluated values, not raw text: a number for a
    # fraction/angle, an element (from a binding or nested form), or a Symbol
    # (from a quote) to be resolved to an element.

    @staticmethod
    def _is_number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _as_float(self, value, what: str) -> float:
        if self._is_number(value):
            return float(value)
        raise CommandError(f"Couldn't read {self._show(value)} as {what}.")

    def _as_fraction(self, value) -> float:
        if not self._is_number(value):
            raise CommandError(
                f"Couldn't read {self._show(value)} as a position. Use a "
                "fraction like 1/3 or a decimal like 0.5."
            )
        fraction = float(value)
        if not 0.0 <= fraction <= 1.0:
            raise CommandError(
                f"Position must be between 0 and 1 (got {fraction:g})."
            )
        return fraction

    def _as_point(self, value) -> PointItem:
        point = self.resolve_point(value.name) if isinstance(value, Symbol) else value
        if isinstance(point, PointItem):
            self._require_live(point)
            if point.is_intersection():
                raise CommandError(
                    "That is an intersection point. It's computed from its "
                    "lines, so a new line can't anchor to it."
                )
            return point
        raise CommandError(f"Expected a point, got {self._show(value)}.")

    def _as_line(self, value) -> LineItem:
        line = self.resolve_line(value.name) if isinstance(value, Symbol) else value
        if isinstance(line, LineItem):
            self._require_live(line)
            return line
        raise CommandError(f"Expected a line, got {self._show(value)}.")

    def _require_live(self, item) -> None:
        if item.scene() is None:
            raise CommandError(
                f"{self._show(item)} no longer exists (it may have been undone "
                "or deleted)."
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
        """Find a point by label (``A``) or by its ``list`` id (``P1``)."""
        points = self._points()  # same order/numbering as the (list) command
        match = _match_by_label(points, name) or _match_by_id(points, name, "p")
        if match is None:
            raise CommandError(
                f"No point named {name!r}. Quote a label (e.g. 'A) or an id "
                "from (list) (e.g. 'P1)."
            )
        if match.is_intersection():
            raise CommandError(
                f"{name!r} is an intersection point. It's computed from its "
                "lines, so a new line can't anchor to it."
            )
        return match

    def resolve_line(self, name: str) -> LineItem:
        """Find a line by label (``a``) or by its ``list`` id (``L1``)."""
        lines = self._lines()
        match = _match_by_label(lines, name) or _match_by_id(lines, name, "l")
        if match is None:
            raise CommandError(
                f"No line named {name!r}. Quote a label (e.g. 'a) or an id "
                "from (list) (e.g. 'L1)."
            )
        return match

    # -- Forms -------------------------------------------------------------

    def _form_quote(self, args, env):
        if len(args) != 1:
            raise CommandError("Usage: (quote <x>)  or  'x")
        return args[0]

    def _form_define(self, args, env):
        if len(args) != 2:
            raise CommandError("Usage: (define <name> <value>)")
        name = args[0]
        if not isinstance(name, Symbol):
            raise CommandError("(define <name> <value>): the name must be a bare word.")
        value = self._eval(args[1], env)
        env.define(name.name, value)
        return value

    def _form_let(self, args, env):
        if not args:
            raise CommandError("Usage: (let ((<name> <value>) …) <body> …)")
        bindings = args[0]
        if not isinstance(bindings, list):
            raise CommandError(
                "(let …): the first part is a list of (<name> <value>) pairs."
            )
        scope = Environment(env)
        for pair in bindings:
            if not (
                isinstance(pair, list)
                and len(pair) == 2
                and isinstance(pair[0], Symbol)
            ):
                raise CommandError("Each let binding is (<name> <value>).")
            scope.define(pair[0].name, self._eval(pair[1], scope))
        result = None
        for body in args[1:]:
            result = self._eval(body, scope)
        return result

    def _form_help(self, args, env) -> str:
        return (
            "Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Numbers evaluate to themselves; a bare word is a binding; 'x quotes\n"
            "a name (element ids and labels are quoted: 'L1, 'A). Forms return the\n"
            "element they make, so they nest: (add line 260 (point 'L1 2/3))\n"
            "\n"
            "  (add point <across> <down>) a point placed on the canvas;\n"
            "                              0 0 = top-left, 1 1 = bottom-right\n"
            "  (add horizon <fraction>)    horizontal, orientation-locked line;\n"
            "                              0 = top of canvas, 1 = bottom\n"
            "  (add line <angle> <point>)  line through a point, at an angle in\n"
            "                              degrees clockwise from horizontal\n"
            "  (add line <point> <point>)  line through two points, bound to both\n"
            "  (point <line> <fraction>)   a point along a line, 0 = its left\n"
            "                              end, 1 = its right; anchored to it\n"
            "  (define <name> <value>)     name a value for later reuse\n"
            "  (let ((<name> <value>) …)   bind names in a local scope, then\n"
            "       <body> …)              evaluate the body (returns the last)\n"
            "  (list [-points | -lines])   list canvas elements\n"
            "  (help)                      show this help\n"
            "\n"
            "Reference an element by quoting its label ('A, 'a) or its id ('P1, 'L1)."
        )

    def _form_add(self, args, env):
        if not args:
            raise CommandError(
                "Usage: (add point <across> <down>), (add line <angle> "
                "<point>), or (add horizon <fraction>)"
            )
        what = args[0]
        if not isinstance(what, Symbol):
            raise CommandError("Usage: (add horizon ...), (add line ...) or (add point ...)")
        key = what.name.lower()
        if key == "horizon":
            return self._add_horizon(args[1:], env)
        if key == "line":
            return self._add_line(args[1:], env)
        if key == "point":
            return self._add_point(args[1:], env)
        raise CommandError(
            f"Don't know how to add {what.name!r}. Try (add point <across> "
            "<down>), (add line <angle> <point>) or (add horizon <fraction>)."
        )

    def _add_point(self, args, env) -> PointItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (add point <across> <down>)\n"
                "  across: 0 = left edge of canvas, 1 = right edge\n"
                "  down:   0 = top of canvas, 1 = bottom\n"
                "  e.g. (add point 1/3 1/3)"
            )
        across = self._as_fraction(self._eval(args[0], env))
        down = self._as_fraction(self._eval(args[1], env))
        return self.scene.add_point_at(across, down)

    def _add_horizon(self, args, env) -> LineItem:
        if not args:
            raise CommandError(
                "Usage: (add horizon <fraction>)\n"
                "  0 = top of canvas, 1 = bottom. e.g. (add horizon 1/3)"
            )
        return self.scene.add_horizon(self._as_fraction(self._eval(args[0], env)))

    def _add_line(self, args, env) -> LineItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (add line <angle> <point>)  - through a point\n"
                "   or: (add line <point> <point>)  - through two points\n"
                "  angle: degrees clockwise from horizontal (e.g. 30, -45)\n"
                "  point: a binding (A), a quoted id ('P1), or a form like "
                "(point 'L1 2/3)"
            )
        first = self._eval(args[0], env)
        if self._is_number(first):
            # (add line <angle> <point>)
            point = self._as_point(self._eval(args[1], env))
            return self.scene.add_line_through(point, float(first))
        # (add line <point> <point>)
        a = self._as_point(first)
        b = self._as_point(self._eval(args[1], env))
        line = self.scene.add_line_between(a, b)
        if line is None:
            raise CommandError(
                "Can't draw a line: those two points are in the same place."
            )
        return line

    def _form_point(self, args, env) -> PointItem:
        if len(args) != 2:
            raise CommandError(
                "Usage: (point <line> <fraction>)\n"
                "  0 = the line's left-hand end, 1 = its right-hand end"
            )
        line = self._as_line(self._eval(args[0], env))
        fraction = self._as_fraction(self._eval(args[1], env))
        point = self.scene.add_point_on_line(line, fraction)
        if point is None:
            raise CommandError("That line doesn't cross the canvas.")
        return point

    def _form_list(self, args, env) -> str:
        show_points = show_lines = True
        if args:
            show_points = show_lines = False
            for arg in args:
                if not isinstance(arg, Symbol):
                    raise CommandError(
                        f"Unknown qualifier: {self._show(arg)}. Use -points or "
                        "-lines."
                    )
                key = arg.name.lower().lstrip("-")
                if key in ("points", "point", "p"):
                    show_points = True
                elif key in ("lines", "line", "l"):
                    show_lines = True
                else:
                    raise CommandError(
                        f"Unknown qualifier: {arg.name!r}. Use -points or -lines."
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
        if isinstance(value, Symbol):
            return value.name
        if self._is_number(value):
            return f"{value:g}"
        if isinstance(value, PointItem):
            return f"{self._point_name(value)}  {self._describe_point(value)}"
        if isinstance(value, LineItem):
            return f"{self._line_name(value)}  {self._describe_line(value)}"
        return str(value)

    def _show(self, value) -> str:
        """A short label for a value, for error messages."""
        if isinstance(value, Symbol):
            return f"'{value.name}"
        if isinstance(value, PointItem):
            return self._point_name(value)
        if isinstance(value, LineItem):
            return self._line_name(value)
        if self._is_number(value):
            return f"{value:g}"
        return repr(value)

    def _point_name(self, point) -> str:
        points = self._points()
        return f"P{points.index(point) + 1}" if point in points else "P?"

    def _line_name(self, line) -> str:
        lines = self._lines()
        return f"L{lines.index(line) + 1}" if line in lines else "L?"

    def _describe_point(self, point) -> str:
        c = point.center()
        label = f'  "{point.label_text()}"' if point.label_text() else ""
        if point.is_intersection():
            tag = "  [intersection]"
        elif point.has_anchor():
            tag = "  [on-line]"
        else:
            tag = ""
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
