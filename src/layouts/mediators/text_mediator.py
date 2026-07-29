"""TextMediator — owns everything specific to the Texto tool: TextToolPanel
wiring (every _on_text_* field -> the selected/draft TextItem), the shared
"Personalizar" pattern picker, arming a draft while the tool is active but
nothing's placed yet, and persisting placed TextItem objects to the project
DB. Mirrors LightMediator/MarkerMediator's style (the mediator wires its own
panels' signals in __init__, instead of MainLayout doing it) rather than the
wall of handlers this used to be directly on MainLayout.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer

from src.canvas.text_item import TextItem
from src.engines.typography import TextProperties, text_properties_to_dict, text_properties_from_dict
from src.layouts.panels.text_panel import TextToolPanel, radius_from_percent
from src.layouts.panels.color_customize_panel import ColorCustomizePanel

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_SYNC_DEBOUNCE_MS = 250


class _PendingText:
    """Stand-in for a not-yet-placed TextItem — lets the Text panel's
    handlers (`_on_text_*`, "Personalizar") write into a real TextProperties
    object while the Texto tool is armed but nothing has been clicked on
    the map yet, using the exact same `it.props.x = ...` / `it.update()`
    call shape they already use for a real selected TextItem."""

    def __init__(self, props: TextProperties):
        self.props = props

    def prepareGeometryChange(self):
        pass

    def update(self):
        pass


class TextMediator:
    """Saves/reloads every TextItem placed on the map, and wires
    TextToolPanel/ColorCustomizePanel to whichever TextItem (or draft) is
    currently being edited."""

    MAP_ID = "default"  # matches BrushMediator/RegionMediator/SpawnMediator

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._items: dict[str, TextItem] = {}  # canvas_items row id -> TextItem

        # Draft properties the Text panel edits while the Texto tool is
        # armed but no item has been placed/selected yet — read by TextTool
        # at the moment a new text box is placed (see _provide_text_properties).
        self._pending_text: _PendingText | None = None
        self._active_color_field = None
        self._active_pattern_key: str | None = None

        panel = TextToolPanel(self._l)
        panel.hide()
        self._l.text_panel = panel
        panel.close_requested.connect(self._close_text_panel)
        panel.content_changed.connect(self._l._reposition)
        panel.font_family_changed.connect(self._on_text_family)
        panel.font_weight_changed.connect(self._on_text_weight)
        panel.font_size_changed.connect(self._on_text_font_size)
        panel.bold_changed.connect(self._on_text_bold)
        panel.italic_changed.connect(self._on_text_italic)
        panel.color_changed.connect(self._on_text_color)
        panel.align_changed.connect(self._on_text_align)
        panel.line_height_changed.connect(self._on_text_line_height)
        panel.letter_spacing_changed.connect(self._on_text_letter_spacing)
        panel.shadow_toggled.connect(self._on_text_shadow_toggled)
        panel.shadow_color_changed.connect(self._on_text_shadow_color)
        panel.shadow_opacity_changed.connect(self._on_text_shadow_opacity)
        panel.shadow_blur_changed.connect(self._on_text_shadow_blur)
        panel.outline_toggled.connect(self._on_text_outline_toggled)
        panel.outline_color_changed.connect(self._on_text_outline_color)
        panel.outline_opacity_changed.connect(self._on_text_outline_opacity)
        panel.outline_width_changed.connect(self._on_text_outline_width)
        panel.glow_toggled.connect(self._on_text_glow_toggled)
        panel.glow_color_changed.connect(self._on_text_glow_color)
        panel.glow_blur_changed.connect(self._on_text_glow_blur)
        panel.curvature_changed.connect(self._on_text_curvature)
        panel.opacity_changed.connect(self._on_text_opacity)
        panel.strikethrough_toggled.connect(self._on_text_strikethrough)
        panel.overline_toggled.connect(self._on_text_overline)
        panel.underline_toggled.connect(self._on_text_underline)
        panel.double_underline_toggled.connect(self._on_text_double_underline)
        panel.box_toggled.connect(self._on_text_box)
        panel.cloud_toggled.connect(self._on_text_cloud)
        panel.serif_toggled.connect(self._on_text_serif)

        # Single shared "Personalizar" picker sub-panel, reused for whichever
        # ColorField (text color, shadow, outline, glow) opens it — same
        # single-instance-reused pattern as RegionEditPanel across zone cards.
        # Rides beside text_panel like RegionEditPanel does beside
        # RegionSettingsPanel — positioned manually in PanelLayoutEngine, not
        # through PanelManager's single-slot layout.
        cc = ColorCustomizePanel(self._l)
        cc.hide()
        self._l.color_customize_panel = cc
        cc.close_requested.connect(self._close_color_customize)
        cc.pattern_changed.connect(self._on_color_customize_pattern_changed)
        panel.color_field.customize_requested.connect(
            lambda: self._open_color_customize("text", panel.color_field)
        )
        panel.shadow_color.customize_requested.connect(
            lambda: self._open_color_customize("shadow", panel.shadow_color)
        )
        panel.outline_color.customize_requested.connect(
            lambda: self._open_color_customize("outline", panel.outline_color)
        )
        panel.glow_color.customize_requested.connect(
            lambda: self._open_color_customize("glow", panel.glow_color)
        )

        self._l.canvas.engine._text_tool.set_properties_provider(self._provide_text_properties)
        self._l.canvas.engine.selection.selection_changed.connect(self._on_selection_for_text_panel)
        self._l.canvas.engine.text_committed.connect(self._close_text_panel)

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._on_history_changed)

        # Placement + undo/redo already go through HistoryEngine (caught
        # above), but retyping an EXISTING text (double-click, not a fresh
        # placement) never touches it — TextTool wires this onto every
        # TextItem's persistent on_edited hook (see text_item.py) so that
        # case is covered too.
        self._l.canvas.engine._text_tool.set_on_edited(self._on_history_changed)

    # ─── Tool arming (called by MainLayout._on_tool_selected) ───

    def _arm_draft(self):
        """Texto tool just became active — give the panel a fresh draft to
        configure before the first click on the map, unless an existing
        TextItem is already selected (nothing to arm then)."""
        if self._text_selected_items():
            return
        self._pending_text = _PendingText(TextProperties(text="Texto", font_size=20, font_weight=600))
        self._l.text_panel.set_values(self._pending_text.props)

    # ─── Targets: real selection, or the not-yet-placed draft ───

    def _text_selected_items(self) -> list:
        return [it for it in self._l.canvas.engine.selection.selected_items if isinstance(it, TextItem)]

    def _text_targets(self) -> list:
        """What the Text panel's controls currently write into: a real
        selected TextItem if one exists, else the not-yet-placed draft
        while the Texto tool is armed, else nothing."""
        items = self._text_selected_items()
        if items:
            return items
        if self._pending_text is not None and self._l.canvas.engine.tool_manager.active_name == "Texto":
            return [self._pending_text]
        return []

    def _provide_text_properties(self):
        """Read by TextTool at the moment a new text box is placed."""
        if self._pending_text is not None:
            return copy.deepcopy(self._pending_text.props)
        return TextProperties(text="Texto", font_size=20, font_weight=600)

    def _on_selection_for_text_panel(self, _ids):
        items = self._text_selected_items()
        if items:
            it = items[0]
            self._l.text_panel.set_values(it.props)
            self._l._panel_mgr.show("Text")
        elif self._l.canvas.engine.tool_manager.active_name != "Texto":
            self._l._panel_mgr.hide("Text")
            self._close_color_customize()
        self._l._reposition()

    def _close_text_panel(self):
        self._l._panel_mgr.hide("Text")
        self._close_color_customize()
        self._pending_text = None
        self._l._reposition()

    # ─── "Personalizar" paint picker ───

    @staticmethod
    def _pattern_target(props, key: str):
        """(object, base-color-attr) pair for a Personalizar key — obj.pattern
        is the PaintGrid, getattr(obj, attr) is the plain fallback hex."""
        return {
            "text": (props, "color"),
            "shadow": (props.shadow, "color"),
            "outline": (props.outline, "color"),
            "glow": (props.glow, "color"),
        }[key]

    def _open_color_customize(self, key: str, field):
        self._active_color_field = field
        self._active_pattern_key = key
        cells = None
        targets = self._text_targets()
        if targets:
            obj, attr = self._pattern_target(targets[0].props, key)
            obj.pattern.ensure(getattr(obj, attr))
            cells = obj.pattern.cells
        self._l.color_customize_panel.load_pattern(cells, field.color())
        self._l.color_customize_panel.show()
        self._l._reposition()

    def _on_color_customize_pattern_changed(self, cells: list):
        if not self._active_pattern_key:
            return
        dominant = cells[0] if cells else self._active_color_field.color()
        for it in self._text_targets():
            obj, attr = self._pattern_target(it.props, self._active_pattern_key)
            obj.pattern.cells = list(cells)
            setattr(obj, attr, dominant)
            it.prepareGeometryChange()
            it.update()
        self._active_color_field.set_color(dominant)

    def _close_color_customize(self):
        self._l.color_customize_panel.hide()
        self._active_color_field = None
        self._active_pattern_key = None
        self._l._reposition()

    # ─── Text Panel field handlers ───

    def _on_text_family(self, family: str):
        for it in self._text_targets():
            it.props.font_family = family
            it.prepareGeometryChange()
            it.update()

    def _on_text_weight(self, weight: int):
        for it in self._text_targets():
            it.props.font_weight = weight
            it.prepareGeometryChange()
            it.update()

    def _on_text_font_size(self, value: float):
        for it in self._text_targets():
            it.props.font_size = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_bold(self, checked: bool):
        for it in self._text_targets():
            it.props.font_weight = 700 if checked else 400
            it.prepareGeometryChange()
            it.update()

    def _on_text_italic(self, checked: bool):
        for it in self._text_targets():
            it.props.italic = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_color(self, color: str):
        for it in self._text_targets():
            it.props.color = color
            it.props.pattern.fill(color)
            it.update()

    def _on_text_align(self, align):
        for it in self._text_targets():
            it.props.align = align
            it.update()

    def _on_text_line_height(self, value: float):
        for it in self._text_targets():
            it.props.spacing.line_height = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_letter_spacing(self, value: float):
        for it in self._text_targets():
            it.props.spacing.letter_spacing = value
            it.prepareGeometryChange()
            it.update()

    # ─── Estilo Panel ───

    def _on_text_shadow_toggled(self, checked: bool):
        for it in self._text_targets():
            it.props.shadow.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_shadow_color(self, color: str):
        for it in self._text_targets():
            it.props.shadow.color = color
            it.props.shadow.pattern.fill(color)
            it.update()

    def _on_text_shadow_opacity(self, percent: float):
        for it in self._text_targets():
            it.props.shadow.opacity = percent / 100.0
            it.update()

    def _on_text_shadow_blur(self, value: float):
        for it in self._text_targets():
            it.props.shadow.blur = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_outline_toggled(self, checked: bool):
        for it in self._text_targets():
            it.props.outline.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_outline_color(self, color: str):
        for it in self._text_targets():
            it.props.outline.color = color
            it.props.outline.pattern.fill(color)
            it.update()

    def _on_text_outline_opacity(self, percent: float):
        for it in self._text_targets():
            it.props.outline.opacity = percent / 100.0
            it.update()

    def _on_text_outline_width(self, value: float):
        for it in self._text_targets():
            it.props.outline.width = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_glow_toggled(self, checked: bool):
        for it in self._text_targets():
            it.props.glow.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_glow_color(self, color: str):
        for it in self._text_targets():
            it.props.glow.color = color
            it.props.glow.pattern.fill(color)
            it.update()

    def _on_text_glow_blur(self, value: float):
        for it in self._text_targets():
            it.props.glow.radius = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_curvature(self, percent: float):
        for it in self._text_targets():
            it.props.curve.enabled = percent > 0
            it.props.curve.radius = radius_from_percent(percent)
            it.prepareGeometryChange()
            it.update()

    def _on_text_opacity(self, percent: float):
        for it in self._text_targets():
            it.props.opacity = percent / 100.0
            it.update()

    # ─── Enfeites ───

    def _on_text_strikethrough(self, checked: bool):
        for it in self._text_targets():
            it.props.strikethrough = checked
            it.update()

    def _on_text_overline(self, checked: bool):
        for it in self._text_targets():
            it.props.overline = checked
            it.update()

    def _on_text_underline(self, checked: bool):
        for it in self._text_targets():
            it.props.underline = checked
            it.update()

    def _on_text_double_underline(self, checked: bool):
        for it in self._text_targets():
            it.props.double_underline = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_box(self, checked: bool):
        for it in self._text_targets():
            it.props.ribbon.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_cloud(self, checked: bool):
        for it in self._text_targets():
            it.props.cloud = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_serif(self, checked: bool):
        for it in self._text_targets():
            it.props.serif = checked
            it.prepareGeometryChange()
            it.update()

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items.clear()
        if not self._uow:
            return

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != "text":
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            item = TextItem(text_properties_from_dict(meta))
            item.setPos(QPointF(row["position_x"], row["position_y"]))
            item.setRotation(row["rotation"] or 0.0)
            item.setZValue(50)
            item.on_edited = self._on_history_changed
            item.setData(1, row["id"])
            scene.addItem(item)
            self._items[row["id"]] = item

    def _on_history_changed(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        """Upserts every currently-placed text item into the project DB,
        and drops rows for ones no longer present (deleted/undone) — same
        shape as BrushMediator/SpawnMediator's own _sync_to_db."""
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            if not isinstance(item, TextItem) or not item.isVisible():
                continue
            fields = dict(
                item_type="text", name=item.props.text[:80],
                position_x=item.pos().x(), position_y=item.pos().y(),
                rotation=item.rotation(),
                metadata=json.dumps(text_properties_to_dict(item.props)),
            )
            row_id = item.data(1)
            # A cached id can go stale (undo hid the item, its row got
            # swept below, then redo brought it back still carrying that
            # dead id) — fall back to creating a fresh row, same as Brush/Spawn.
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            item.on_edited = self._on_history_changed
            self._items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._items[stale_id]
