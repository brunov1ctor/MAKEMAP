"""TextItem — a text object on the canvas: draggable, rotatable, selectable,
editable in place (double-click), and highlighted on hover, matching the
interaction model of a professional design tool's text tool."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsTextItem, QStyle,
    QGraphicsSceneMouseEvent, QGraphicsSceneHoverEvent,
)

from src.engines.typography import TextProperties, TypographyRenderer


class _InlineTextEditor(QGraphicsTextItem):
    """Temporary child editor used while a TextItem is being typed into.

    A real subclass (rather than monkey-patching focusOutEvent on a plain
    QGraphicsTextItem) so Qt's virtual dispatch reliably calls back into the
    owner to commit the edit when focus leaves — e.g. clicking elsewhere on
    the canvas to place/select something else.
    """

    def __init__(self, owner: "TextItem", text: str, parent=None):
        super().__init__(text, parent)
        self._owner = owner

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._owner._finish_editing()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.clearFocus()
            return
        super().keyPressEvent(event)


class TextItem(QGraphicsItem):
    """Renders a TextProperties via TypographyRenderer.

    Local (0, 0) is the visual *center* of the rendered text (not its
    top-left) so that TransformEngine.rotate — which spins an item's content
    around its own transform origin while separately relocating item.pos()
    around the rotation center — keeps a single selected text item rotating
    in place instead of drifting.
    """

    HOVER_PAD = 6.0

    def __init__(self, props: TextProperties | None = None, parent=None):
        super().__init__(parent)
        self.props = props or TextProperties(text="Texto")
        self._hovered = False
        self._editor: _InlineTextEditor | None = None
        self.on_commit = None  # one-shot callback fired by the next _finish_editing()

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        self.setData(0, {"item_type": "text"})

    # --- Geometry (centered on local origin) ---

    def _text_rect(self) -> QRectF:
        """Bounding rect of the rendered text, centered at local (0, 0)."""
        rect = TypographyRenderer.bounding_rect(self.props)
        return rect.translated(-rect.center())

    def _render_offset(self) -> QPointF:
        """Where to tell TypographyRenderer to draw so it lands centered."""
        rect = TypographyRenderer.bounding_rect(self.props)
        return QPointF(-rect.center().x(), -rect.center().y())

    def boundingRect(self) -> QRectF:
        pad = self.HOVER_PAD
        return self._text_rect().adjusted(-pad, -pad, pad, pad)

    def selection_bounding_rect(self) -> QRectF:
        """Tight bounds around the rendered glyphs, without boundingRect()'s
        extra hover margin — used by TransformEngine so the purple selection
        border/handles hug the visible text instead of floating outside it."""
        return self._text_rect()

    # --- Painting ---

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        if self._editor is None:
            TypographyRenderer.render(painter, self._render_offset(), self.props)
        if self._hovered and not self.isSelected():
            pen = QPen(QColor(79, 195, 247, 220), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._text_rect().adjusted(-3, -3, 3, 3))

    # --- Hover highlight ---

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
        self._hovered = True
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
        self._hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().hoverLeaveEvent(event)

    # --- Inline editing (double-click to type) ---

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        self.start_editing()
        super().mouseDoubleClickEvent(event)

    def start_editing(self):
        if self._editor is not None:
            return
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        editor = _InlineTextEditor(self, self.props.text, self)
        editor.setFont(TypographyRenderer.build_font(self.props))
        editor.setDefaultTextColor(QColor(self.props.color))
        editor.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        editor.setPos(self._text_rect().topLeft())
        editor.setZValue(1)
        self._editor = editor
        self.prepareGeometryChange()
        self.update()

        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        editor.setTextCursor(cursor)

    def _finish_editing(self):
        editor = self._editor
        if editor is None:
            return
        new_text = editor.toPlainText()
        self._editor = None
        if self.scene():
            self.scene().removeItem(editor)
        self.props.text = new_text.strip() or self.props.text
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.prepareGeometryChange()
        self.update()

        callback, self.on_commit = self.on_commit, None
        if callback:
            callback()
