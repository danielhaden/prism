"""Writing the canvas out as SVG.

Vector, not pixels: a projective figure is lines and small discs, and it
should stay sharp at any size it is printed or embedded at.

What is written is **what the view shows** — the same framing, the same
clipping of infinite lines at the edge. **View > Fit to Frame** (Ctrl+0)
first to export the reference frame instead.
"""

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgGenerator


def export_svg(view: object, path: str, title: str = "Prism drawing") -> bool:
    """Write what ``view`` is showing to an SVG file.

    Three things this does that rendering the scene alone would not:

    * **Paints the background.** The brush lives on the view, so a plain
      scene render leaves it out — and a point's glow is a disc *in the
      background colour*, drawn over the lines to cut them away behind the
      dot. On transparency those discs become grey blobs.
    * **Renders the scene, not the view**, so the view's own chrome stays
      out of the file — the arrows marking off-screen points are a way of
      finding them, not part of the drawing.
    * **Lifts the selection** for the duration. Selected items draw
      highlighted, and nobody wants that in an exported figure.

    Args:
        view: The :class:`~prism.canvas.view.CanvasView` to write.
        path: Where to write it.
        title: The SVG's title element.

    Returns:
        Whether it was written.

    Raises:
        OSError: If the file can't be written.
    """
    scene = view.scene()
    if scene is None:
        return False
    viewport = view.viewport().rect()
    if viewport.isEmpty():
        return False
    source = view.mapToScene(viewport).boundingRect()
    target = QRectF(0, 0, viewport.width(), viewport.height())

    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(viewport.size())
    generator.setViewBox(QRect(0, 0, viewport.width(), viewport.height()))
    generator.setTitle(title)
    generator.setDescription(
        "A projective-geometry drawing made in Prism. Lines are infinite; "
        "what is drawn here is clipped to the exported view."
    )

    held = list(scene.selectedItems())
    painter = QPainter()
    if not painter.begin(generator):
        raise OSError(f"Couldn't open {path} for writing")
    try:
        for item in held:
            item.setSelected(False)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.fillRect(target, view.backgroundBrush())
        scene.render(painter, target, source, Qt.KeepAspectRatio)
    finally:
        painter.end()
        for item in held:
            if item.scene() is scene:
                item.setSelected(True)
    return True
