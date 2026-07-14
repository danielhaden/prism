"""Command interpreter for the canvas console.

Parses a typed command line and runs it against the scene. Commands are
registered in a dict so new ones are easy to add as the console grows into a
scripting surface.
"""

from prism.items import LineItem, PointItem


class CommandInterpreter:
    def __init__(self, scene):
        self.scene = scene
        self._commands = {
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
            "  list [-points | -lines]   list canvas elements "
            "(all if no qualifier)\n"
            "  help                       show this help"
        )

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
        if ln.has_pivot():
            parts.append("pivot")
        if ln.label_text():
            parts.append(f'"{ln.label_text()}"')
        return "  ".join(parts)
