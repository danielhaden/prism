"""Command interpreter for the canvas console.

Parses a typed command line and runs it against the scene. Commands are
registered in a dict so new ones are easy to add as the console grows into a
scripting surface.
"""

from prism.items import LineItem, PointItem


def parse_fraction(text: str):
    """Read a 0-1 position written as a fraction or a decimal.

    Accepts forms like ``1/2``, ``2/3``, ``0.5`` or ``.25``.

    Returns:
        The value as a float, or None if it can't be read.
    """
    text = text.strip()
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
        self._commands = {
            "add": self._cmd_add,
            "list": self._cmd_list,
            "help": self._cmd_help,
        }

    # -- Entry point -------------------------------------------------------

    def execute(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        parts = line.split()
        name, args = parts[0].lower(), parts[1:]
        handler = self._commands.get(name)
        if handler is None:
            return f"Unknown command: {name!r}. Type 'help'."
        try:
            return handler(args)
        except Exception as exc:  # keep the console alive on any error
            return f"Error: {exc}"

    def command_names(self):
        return sorted(self._commands)

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

    # -- Commands ----------------------------------------------------------

    def _cmd_help(self, args) -> str:
        return (
            "Commands:\n"
            "  add horizon <fraction>    add a horizontal, orientation-locked\n"
            "                            line; 0 = top of canvas, 1 = bottom\n"
            "                            (e.g. 'add horizon 1/3' or '0.5')\n"
            "  list [-points | -lines]   list canvas elements "
            "(all if no qualifier)\n"
            "  help                      show this help"
        )

    def _cmd_add(self, args) -> str:
        if not args:
            return "Usage: add horizon <fraction>"
        what = args[0].lower()
        if what == "horizon":
            return self._add_horizon(args[1:])
        return f"Don't know how to add {args[0]!r}. Try 'add horizon <fraction>'."

    def _add_horizon(self, args) -> str:
        if not args:
            return (
                "Usage: add horizon <fraction>\n"
                "  0 = top of canvas, 1 = bottom. e.g. 'add horizon 1/3', "
                "'add horizon 0.5'"
            )
        fraction = parse_fraction(args[0])
        if fraction is None:
            return (
                f"Couldn't read {args[0]!r} as a position. "
                "Use a fraction like 1/3 or a decimal like 0.5."
            )
        if not 0.0 <= fraction <= 1.0:
            return (
                f"Position must be between 0 and 1 (got {fraction:g}). "
                "0 = top of canvas, 1 = bottom."
            )
        line = self.scene.add_horizon(fraction)
        y = line.scene_line().y1()
        return f"Added horizon at {args[0]} down the canvas (y = {y:.1f})."

    def _cmd_list(self, args) -> str:
        show_points = show_lines = True
        if args:
            show_points = show_lines = False
            for arg in args:
                key = arg.lower().lstrip("-")
                if key in ("points", "point", "p"):
                    show_points = True
                elif key in ("lines", "line", "l"):
                    show_lines = True
                else:
                    return f"Unknown qualifier: {arg!r}. Use -points or -lines."

        blocks = []
        if show_points:
            blocks.append(self._list_points())
        if show_lines:
            blocks.append(self._list_lines())
        return "\n".join(blocks)

    def _list_points(self) -> str:
        points = self._points()
        lines = [f"Points ({len(points)}):"]
        for i, point in enumerate(points, 1):
            c = point.center()
            label = f'  "{point.label_text()}"' if point.label_text() else ""
            kind = "  [intersection]" if point.is_derived else ""
            lines.append(f"  P{i}  ({c.x():.1f}, {c.y():.1f}){label}{kind}")
        if not points:
            lines.append("  (none)")
        return "\n".join(lines)

    def _list_lines(self) -> str:
        items = self._lines()
        lines = [f"Lines ({len(items)}):"]
        for i, ln in enumerate(items, 1):
            lines.append(f"  L{i}  {self._describe_line(ln)}")
        if not items:
            lines.append("  (none)")
        return "\n".join(lines)

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
