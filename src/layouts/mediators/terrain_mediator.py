"""TerrainMediator — terrain panel ↔ canvas engine wiring.

Built around the same "Nova Região"-style split as RegionMediator: "+ Novo
Terreno" opens TerrainEditPanel with a live preview boundary on the canvas
(name/forma/dimensões/imagem/cor da borda all apply immediately), and only
"Salvar Terreno" turns that into a real TerrainCard + persisted row. Clicking
an existing card's "Editar" reopens the same sub painel, pre-filled, and
field edits from then on auto-persist (see _maybe_persist) instead of
needing a second "Salvar".
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor, QCursor, QPixmap

from src.canvas.map_boundary import MapBoundary
from src.canvas.neon_preview_overlay import NeonPreviewOverlay
from src.canvas.vertex_handles_overlay import VertexHandlesOverlay
from src.canvas.point_alignment_guides import PointAlignmentGuides
from src.layouts.panels.terrain.panel import TerrainSettingsPanel
from src.layouts.panels.terrain.terrain_edit_panel import TerrainEditPanel
from src.services.project_assets import import_asset, resolve_asset_path

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


@dataclass
class _Terrain:
    id: str
    name: str
    shape: str = "rectangle"
    width: int = 4096
    height: int = 4096
    color: QColor = field(default_factory=lambda: QColor(79, 195, 247))
    image_path: str = ""
    points: list[tuple[float, float]] = field(default_factory=list)  # only for shape == "freehand"
    curve_controls: dict[int, tuple[float, float]] = field(default_factory=dict)  # segment index -> control point


class TerrainMediator:
    """Manages terrain panel ↔ canvas engine connections."""

    _STAGGER_STEP = 120.0
    _STAGGER_WRAP = 8
    MAP_ID = "default"  # matches Região/Brush — none of these are scoped to the (unimplemented) maps/worlds hierarchy
    DEFAULT_SHAPE = "rectangle"
    DEFAULT_WIDTH = 4096
    DEFAULT_HEIGHT = 4096
    VERTEX_SNAP_TOLERANCE_M = 60.0  # how close a click must land to an existing corner to "grab" it

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._boundaries: dict[str, MapBoundary] = {}
        self._terrains: dict[str, _Terrain] = {}
        self._active_id: str | None = None
        self._is_creating = False
        self._color_idx = 0

        # "Livre" freehand drawing — see _on_freehand_started/_finished.
        self._prev_tool_name: str | None = None
        # Insert-mode state (editing an EXISTING preset/freehand shape's
        # corners instead of drawing a brand new polygon from scratch) —
        # see _on_freehand_started/_handle_insert_point/_spliced_vertices.
        self._edit_base_vertices: list[QPointF] | None = None
        self._insert_anchor_index: int | None = None
        self._inserted_points: list[QPointF] = []
        self._neon_overlay = None  # NeonPreviewOverlay | None — see _neon_chain
        self._vertex_handles = None  # VertexHandlesOverlay | None — see _all_current_vertices
        self._alignment_guides = None  # PointAlignmentGuides | None
        self._freehand_badge_timer = QTimer()
        self._freehand_badge_timer.setInterval(16)
        self._freehand_badge_timer.timeout.connect(self._update_freehand_badge_pos)

        # Which parallax preset (if any) is currently the live background —
        # so an edit made in the Config panel (rename/add layer/JSON import/
        # reorder) can refresh the canvas immediately instead of leaving it
        # showing a stale snapshot from before the edit.
        self._active_parallax_key: str | None = None
        from src.engines.map.parallax import get_parallax_library
        get_parallax_library().changed.connect(self._on_parallax_library_changed)

        panel = TerrainSettingsPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_terrain_panel)
        self._l.terrain_panel = panel

        panel.infinite_toggled.connect(self.on_infinite)
        panel.infinite_blocked.connect(lambda: self._l.info_modal.show_message(
            "🌍 Crie um terreno para definir os limites do mapa.\n\nClique em \"+ Novo Terreno\" para começar."
        ))
        panel.terrain_add_requested.connect(self.on_add_requested)
        panel.terrain_removed.connect(self.on_removed)
        panel.terrain_delete_requested.connect(self._on_delete_requested)
        panel.terrain_selected.connect(self.on_selected)
        panel.terrain_edit_requested.connect(self.on_edit_requested)
        panel.terrain_locate_requested.connect(self.on_locate)
        panel.terrain_renamed.connect(self.on_renamed)
        # Deferred — same reasoning as Região's card list: a freshly
        # inserted TerrainCard's sizeHint() isn't settled synchronously.
        panel.content_changed.connect(lambda: QTimer.singleShot(0, self._l._reposition))
        # Compass HUD shows the map's own size (from this panel) alongside
        # the brush's active "Pintando em" terrain name (from BrushMediator
        # — see brush_mediator.py's own compass-refresh wiring) — a rename
        # here can change that terrain's display name too, so keep it live.
        panel.terrain_renamed.connect(lambda _id, _name: self._l._refresh_compass_hud())

        edit_panel = TerrainEditPanel(self._l)
        edit_panel.hide()
        edit_panel.content_changed.connect(self._l._reposition)
        self._l.terrain_edit_panel = edit_panel
        edit_panel.name_changed.connect(self._on_name_changed)
        edit_panel.shape_changed.connect(self._on_shape_changed)
        edit_panel.dimensions_changed.connect(self._on_dims_changed)
        edit_panel.image_changed.connect(self._on_image_changed)
        edit_panel.border_color_changed.connect(self._on_color_changed)
        edit_panel.close_requested.connect(self.on_close_edit)
        edit_panel.save_requested.connect(self.on_save_requested)
        edit_panel.freehand_started.connect(self._on_freehand_started)
        edit_panel.freehand_finished.connect(self._on_freehand_finished)

        # Map boundary overlays reference
        self._l._terrain_boundaries = self.boundaries

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        for boundary in self._boundaries.values():
            boundary.hide()
        self._boundaries.clear()
        self._terrains.clear()
        self._l.terrain_panel.clear_terrains()
        if not self._uow:
            self._sync_all_boundaries()
            return

        scene = self._l.canvas.engine.viewport.scene()
        rows = self._uow.terrains.get_by_map(self.MAP_ID)
        if rows and self._l.terrain_panel.is_infinite:
            self._l.terrain_panel.set_infinite(False)
        for row in rows:
            color = QColor(row["color"]) if row["color"] else QColor(79, 195, 247)
            terrain_id = row["id"]
            points_raw = json.loads(row["points_json"] or "[]")
            curve_raw = json.loads(row["curve_controls_json"] or "{}")
            terr = _Terrain(
                id=terrain_id, name=row["name"], shape=row["shape"] or "rectangle",
                width=row["width"], height=row["height"], color=color,
                image_path=row["image_path"] or "", points=[tuple(p) for p in points_raw],
                curve_controls={int(k): tuple(v) for k, v in curve_raw.items()},
            )
            self._terrains[terrain_id] = terr

            boundary = MapBoundary(scene, color)
            if row["visible"] and not self._l.terrain_panel.is_infinite:
                if terr.shape == "freehand" and terr.points:
                    curve_controls = {i: QPointF(x, y) for i, (x, y) in terr.curve_controls.items()}
                    boundary.set_points([QPointF(x, y) for x, y in terr.points], curve_controls)
                else:
                    boundary.show(terr.width, terr.height, terr.shape)
                boundary.set_position(QPointF(row["position_x"], row["position_y"]))
            boundary.set_on_position_changed(
                lambda pos, tid=terrain_id: self._on_boundary_moved(tid, pos)
            )
            self._boundaries[terrain_id] = boundary

            photo = self._load_photo(terr.image_path)
            self._l.terrain_panel.add_terrain_card(
                terrain_id, terr.name, terr.color,
                area_m2=self._area_m2(terr), object_count=self._count_objects_in(terr),
                photo=photo,
            )
        self._sync_all_boundaries()

    def _on_boundary_moved(self, terrain_id: str, pos: QPointF):
        if self._uow:
            self._uow.terrains.update(terrain_id, position_x=pos.x(), position_y=pos.y())

    def on_renamed(self, terrain_id: str, new_name: str):
        terr = self._terrains.get(terrain_id)
        if terr:
            terr.name = new_name
        if self._uow:
            self._uow.terrains.update(terrain_id, name=new_name)
        if self._active_id == terrain_id:
            self._l.terrain_edit_panel.set_name(new_name)
        # Atualiza o label de terreno nos painéis que o exibem.
        self._l.brush_panel.set_terrain_options(self._terrain_name_options())
        self._l.region_edit_panel.set_terrain_label(
            terrain_id, new_name
        )

    @property
    def boundaries(self):
        return self._boundaries

    def _stagger_offset(self) -> QPointF:
        """Offsets each newly created terrain's spawn point away from the
        view center so it doesn't land exactly on top of an existing
        bounded terrain."""
        n = len(self._boundaries) % self._STAGGER_WRAP
        return QPointF(self._STAGGER_STEP * n, self._STAGGER_STEP * n)

    def _sync_all_boundaries(self):
        """Keeps the brush tool's full boundary list current so the grid
        overlay can clip across every bounded terrain at once (see
        CanvasEngine._update_grid), not just whichever one is selected."""
        self._l.canvas.engine._brush_tool.set_all_boundaries(list(self._boundaries.values()))
        self._l.canvas.engine._update_grid()

    def on_infinite(self, infinite: bool):
        if infinite:
            self._l.canvas.engine.clear_map_bounds()
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
            for boundary in self._boundaries.values():
                boundary.hide()
            # Sincroniza todos os painéis para "Mapa Infinito".
            self._l.brush_panel.set_active_terrain("")
            self._l.region_edit_panel.set_terrain_label("", "")
            self._l._text_med.set_active_terrain("")
            self._l._marker_med.set_active_terrain("")
            self._l._spawn_med.set_active_terrain("")
            self._l._light_med.set_active_terrain("")
            self._l._refresh_compass_hud()
        else:
            # Ativa o modo finito — define bounds genéricos para que
            # BrushTool.on_bounds_missing dispare se nenhum terreno estiver selecionado.
            self._l.canvas.engine.set_map_bounds(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT, self.DEFAULT_SHAPE)
            for tid, boundary in self._boundaries.items():
                terr = self._terrains.get(tid)
                if not terr:
                    continue
                if terr.shape == "freehand" and terr.points:
                    curve_controls = {
                        i: QPointF(x, y)
                        for i, (x, y) in terr.curve_controls.items()
                    }
                    boundary.set_points(
                        [QPointF(x, y) for x, y in terr.points], curve_controls
                    )
                else:
                    boundary.show(terr.width, terr.height, terr.shape)
            sel_id = self._l.terrain_panel.selected_terrain_id
            if sel_id:
                self._l.canvas.engine._brush_tool.set_active_boundary(
                    self._boundaries.get(sel_id)
                )
                # Sincroniza todos os painéis para o terreno selecionado.
                terr = self._terrains.get(sel_id)
                terrain_name = terr.name if terr else ""
                self._l.brush_panel.set_active_terrain(sel_id)
                self._l.region_edit_panel.set_terrain_label(sel_id, terrain_name)
                self._l._text_med.set_active_terrain(sel_id)
                self._l._marker_med.set_active_terrain(sel_id)
                self._l._spawn_med.set_active_terrain(sel_id)
                self._l._light_med.set_active_terrain(sel_id)
            self._l._refresh_compass_hud()
        self._sync_all_boundaries()
        self._l._reposition()

    def on_selected(self, terrain_id: str):
        boundary = self._boundaries.get(terrain_id)
        if not self._l.terrain_panel.is_infinite:
            # Ensure the boundary is visible — it may have been hidden
            # while in infinite mode and never shown since.
            if boundary and not boundary.visible:
                terr = self._terrains.get(terrain_id)
                if terr:
                    if terr.shape == "freehand" and terr.points:
                        curve_controls = {
                            i: QPointF(x, y)
                            for i, (x, y) in terr.curve_controls.items()
                        }
                        boundary.set_points(
                            [QPointF(x, y) for x, y in terr.points], curve_controls
                        )
                    else:
                        boundary.show(terr.width, terr.height, terr.shape)
            self._l.canvas.engine._brush_tool.set_active_boundary(boundary)
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
        self._l.canvas.engine._update_grid()
        self._l.brush_panel.set_active_terrain(terrain_id)
        terr = self._terrains.get(terrain_id)
        terrain_name = terr.name if terr else ""
        self._l.region_edit_panel.set_terrain_label(terrain_id, terrain_name)
        self._l._text_med.set_active_terrain(terrain_id)
        self._l._marker_med.set_active_terrain(terrain_id)
        self._l._spawn_med.set_active_terrain(terrain_id)
        self._l._light_med.set_active_terrain(terrain_id)
        self._l._refresh_compass_hud()

    def on_locate(self, terrain_id: str):
        """"Localizar" from a card's "..." menu — pans to the terreno's
        center without touching the current zoom level, same convention
        as RegionMediator.on_locate."""
        boundary = self._boundaries.get(terrain_id)
        if not boundary or not boundary._item:
            return
        center = boundary._item.mapToScene(boundary._item.boundingRect().center())
        self._l.canvas.engine.viewport.center_on_point(center)

    def _on_delete_requested(self, terrain_id: str):
        """Mostra modal de confirmação antes de excluir o terreno e sua pintura."""
        terr = self._terrains.get(terrain_id)
        name = terr.name if terr else "este terreno"

        def _confirm():
            card = self._l.terrain_panel.get_card(terrain_id)
            if card:
                card.deleted.emit(terrain_id)

        self._l.info_modal.show_confirm(
            f'⚠ Excluir "{name}"?\n\nToda a pintura deste terreno será apagada permanentemente.',
            confirm_label="Excluir",
            on_confirm=_confirm,
        )
        self._l._reposition()

    def on_removed(self, terrain_id: str):
        boundary = self._boundaries.pop(terrain_id, None)
        self._terrains.pop(terrain_id, None)
        if self._uow:
            self._uow.terrains.delete(terrain_id)

        # Se não há mais terrenos, volta para mapa infinito automaticamente
        # e sincroniza todos os painéis diretamente.
        if not self._terrains and not self._l.terrain_panel.is_infinite:
            if boundary:
                boundary.hide()
            self._l.terrain_panel.set_infinite(True)
            # set_infinite emite infinite_toggled → on_infinite, mas
            # garantimos a sincronização aqui também para não depender
            # da ordem de execução dos signals.
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
            self._l.brush_panel.set_active_terrain("")
            self._l.region_edit_panel.set_terrain_label("", "")
            self._l._text_med.set_active_terrain("")
            self._l._marker_med.set_active_terrain("")
            self._l._spawn_med.set_active_terrain("")
            self._l._light_med.set_active_terrain("")
            self._l._refresh_compass_hud()
            if self._active_id == terrain_id:
                self.on_close_edit()
            self._sync_all_boundaries()
            self._l._reposition()
            return

        # Ainda há terrenos — remove o boundary (e sua pintura junto).
        if boundary:
            boundary.hide()

        if self._active_id == terrain_id:
            self.on_close_edit()

        if not self._l.terrain_panel.is_infinite:
            sel_id = self._l.terrain_panel.selected_terrain_id
            if not sel_id or sel_id == terrain_id:
                next_id = next(iter(self._terrains), None)
                if next_id:
                    self._l.terrain_panel.select_terrain(next_id)
                    return
            self._l.canvas.engine._brush_tool.set_active_boundary(
                self._boundaries.get(self._l.terrain_panel.selected_terrain_id)
            )
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
        self._sync_all_boundaries()

    def on_background(self, bg_type: str, value: str):
        viewport = self._l.canvas.engine.viewport
        self._active_parallax_key = value if bg_type == "parallax" else None
        if bg_type == "none":
            viewport.set_background(None, None)
        elif bg_type == "color":
            viewport.set_background(QColor(value), None)
        elif bg_type == "image":
            pix = QPixmap(value)
            if not pix.isNull():
                viewport.set_background(None, pix)
            else:
                viewport.set_background(None, None)
        elif bg_type == "parallax":
            from src.engines.map.parallax import get_parallax_library
            preset = get_parallax_library().get_preset(value)
            if preset and preset.layers:
                viewport.set_parallax_layers(preset.layers)
            else:
                viewport.clear_parallax()

    def _on_parallax_library_changed(self):
        """Re-applies the currently active parallax preset whenever its data
        changes (Config panel edits, JSON import, layer reorder, etc.) — so
        the canvas stays in sync without the user having to reselect the
        preset in the Terrain panel."""
        if self._active_parallax_key:
            self.on_background("parallax", self._active_parallax_key)

    # ─── "+ Novo Terreno" → configure fields → "Salvar" → card appears ───
    # A live boundary preview exists on the canvas the whole time (same
    # split as Região: layer/boundary created immediately, card+persist
    # only on Salvar) so shape/size/color choices are visible right away.

    # ─── "Livre" freehand drawing ───
    # Two modes, decided by where the FIRST click lands:
    #  - Insert-mode: the first click grabs an existing corner of the
    #    terreno's current shape (preset or already-"Livre") — every click
    #    after that is a NEW point spliced in right after that corner, so
    #    e.g. a square + one inserted point becomes a 5-sided polygon.
    #  - Fresh mode (phase 1/2, unchanged): first click lands anywhere
    #    else — draws a brand new polygon from scratch, discarding
    #    whatever shape was there before.

    def _on_freehand_started(self):
        terr = self._current_terrain()
        if not terr:
            return
        self._reset_freehand_edit_state()
        boundary = self._boundaries.get(terr.id)
        if boundary:
            verts = boundary.polygon_vertices_scene()
            if verts and len(verts) >= 3:
                self._edit_base_vertices = verts

        tool = self._l.canvas.engine._terrain_freehand_tool
        tool.on_point_added = self._on_freehand_point_added
        tool.on_point_moved = self._on_freehand_point_moved
        tool.on_preview_changed = self._on_freehand_preview
        # Curve editing (right-click-drag on the latest segment) only ever
        # applies to a fresh-mode session — insert-mode splices new points
        # into an existing vertex list, where segment indices don't map
        # 1:1 onto a simple curve dict once merged, so it's left alone
        # there (any pre-existing curves just drop when the shape gets
        # restructured by an insert-mode edit — see _on_freehand_finished).
        tool.on_curve_changed = self._on_freehand_curve_changed if self._edit_base_vertices is None else None
        # Esc discards the whole in-progress drawing (points placed so
        # far included) — same as closing the edit panel mid-draw, not a
        # "finish" like clicking the pencil icon again.
        tool.on_escape = self._cancel_freehand_if_active
        self._prev_tool_name = self._l.canvas.engine.tool_manager.active_name
        self._l.canvas.engine.tool_manager.activate(tool.name)
        self._l.freehand_badge.reset(editable=self._edit_base_vertices is not None)
        self._l.freehand_badge.show()
        self._l.freehand_badge.raise_()
        self._freehand_badge_timer.start()
        scene = self._l.canvas.engine.viewport.scene()
        self._neon_overlay = NeonPreviewOverlay(scene)
        self._vertex_handles = VertexHandlesOverlay(scene)
        self._vertex_handles.set_points(self._all_current_vertices())
        self._alignment_guides = PointAlignmentGuides(scene)

    def _all_current_vertices(self) -> list[QPointF]:
        """Every corner of the shape as it stands right now — the WHOLE
        shape, unlike _neon_chain (which only ever highlights the newest
        part) — same "these are the corners" idea as the Select tool's own
        hover handles, see VertexHandlesOverlay."""
        if self._edit_base_vertices is not None:
            if self._insert_anchor_index is None:
                return list(self._edit_base_vertices)
            return self._spliced_vertices(self._inserted_points)
        return self._l.canvas.engine._terrain_freehand_tool.points

    def _neon_chain(self, preview_point: QPointF | None = None) -> list[QPointF]:
        """The part of the shape currently "under construction" — for the
        overlay's pulsing highlight. Insert-mode: the grabbed anchor plus
        whatever's been inserted after it. Fresh mode: every click placed
        so far. Either way, `preview_point` (the cursor's live snapped
        position) tacks on the not-yet-confirmed next segment."""
        if self._edit_base_vertices is not None:
            if self._insert_anchor_index is None:
                return []
            anchor = self._edit_base_vertices[self._insert_anchor_index]
            chain = [anchor] + list(self._inserted_points)
        else:
            chain = self._l.canvas.engine._terrain_freehand_tool.points
        if preview_point is not None:
            chain = chain + [preview_point]
        return chain

    def _nearest_vertex_index(self, vertices: list[QPointF], pos: QPointF) -> int | None:
        best_idx, best_dist = None, self.VERTEX_SNAP_TOLERANCE_M
        for i, v in enumerate(vertices):
            d = math.hypot(v.x() - pos.x(), v.y() - pos.y())
            if d <= best_dist:
                best_idx, best_dist = i, d
        return best_idx

    def _spliced_vertices(self, extra_points: list[QPointF]) -> list[QPointF]:
        """The base shape's corners with `extra_points` inserted right
        after the grabbed anchor corner."""
        verts = list(self._edit_base_vertices)
        idx = self._insert_anchor_index
        return verts[:idx + 1] + list(extra_points) + verts[idx + 1:]

    def _refresh_vertex_handles(self):
        if self._vertex_handles:
            self._vertex_handles.set_points(self._all_current_vertices())

    def _handle_insert_point(self, pos: QPointF):
        if self._insert_anchor_index is None:
            idx = self._nearest_vertex_index(self._edit_base_vertices, pos)
            if idx is None:
                # First click missed every corner — this isn't an edit
                # after all, fall back to drawing a fresh polygon using
                # just this click.
                self._edit_base_vertices = None
                self._l.freehand_badge.reset(editable=False)
                terr = self._current_terrain()
                boundary = self._boundaries.get(terr.id) if terr else None
                if boundary:
                    boundary.set_points([pos])
                if self._neon_overlay:
                    self._neon_overlay.set_chain(self._neon_chain())
                self._refresh_vertex_handles()
                if self._alignment_guides:
                    self._alignment_guides.clear()
                return
            self._insert_anchor_index = idx
            if self._neon_overlay:
                self._neon_overlay.set_chain(self._neon_chain())
            self._refresh_vertex_handles()
            if self._alignment_guides:
                self._alignment_guides.clear()
            return
        self._inserted_points.append(pos)
        terr = self._current_terrain()
        boundary = self._boundaries.get(terr.id) if terr else None
        if boundary:
            boundary.set_points(self._spliced_vertices(self._inserted_points))
        if self._neon_overlay:
            self._neon_overlay.set_chain(self._neon_chain())
        self._refresh_vertex_handles()
        if self._alignment_guides:
            self._alignment_guides.clear()

    def _current_curve_controls(self) -> dict[int, QPointF]:
        """Fresh-mode only — see the on_curve_changed wiring note in
        _on_freehand_started for why insert-mode never has any."""
        if self._edit_base_vertices is not None:
            return {}
        return self._l.canvas.engine._terrain_freehand_tool.curve_controls

    def _on_freehand_point_added(self, points: list[QPointF]):
        terr = self._current_terrain()
        if not terr:
            return
        if self._edit_base_vertices is not None:
            self._handle_insert_point(points[-1])
            return
        boundary = self._boundaries.get(terr.id)
        if boundary:
            boundary.set_points(points, self._current_curve_controls())
        if self._neon_overlay:
            self._neon_overlay.set_chain(self._neon_chain())
        self._refresh_vertex_handles()
        if self._alignment_guides:
            self._alignment_guides.clear()

    def _on_freehand_point_moved(self, points: list[QPointF]):
        """TerrainFreehandTool.on_point_moved — the LAST placed point was
        dragged to a new position (not a new point). Insert-mode: only
        matters if at least one point has already been inserted after the
        anchor (the anchor itself, points[0], isn't draggable — it's a
        grabbed EXISTING corner, not something this session created)."""
        terr = self._current_terrain()
        if not terr:
            return
        boundary = self._boundaries.get(terr.id)
        if self._edit_base_vertices is not None:
            if not self._inserted_points:
                return
            self._inserted_points[-1] = points[-1]
            if boundary:
                boundary.set_points(self._spliced_vertices(self._inserted_points))
        else:
            if boundary:
                boundary.set_points(points, self._current_curve_controls())
        if self._neon_overlay:
            self._neon_overlay.set_chain(self._neon_chain())
        self._refresh_vertex_handles()
        if self._alignment_guides:
            self._alignment_guides.clear()

    def _on_freehand_curve_changed(self, segment_index: int, control: QPointF):
        """Right-click-drag bowed a segment into a curve — fresh-mode
        only (see on_curve_changed wiring in _on_freehand_started)."""
        terr = self._current_terrain()
        if not terr:
            return
        boundary = self._boundaries.get(terr.id)
        if boundary:
            tool = self._l.canvas.engine._terrain_freehand_tool
            boundary.set_points(tool.points, tool.curve_controls)

    def _on_freehand_preview(self, points: list[QPointF], preview_pos: QPointF,
                              distance_m: float | None, angle_deg: float | None):
        """Live rubber-band segment (last confirmed point → cursor) plus
        the CAD-style distance/angle readout on the badge — mirrors
        _on_freehand_point_added but with an extra, not-yet-confirmed
        vertex appended so the in-progress edge is visible before it's
        actually clicked."""
        terr = self._current_terrain()
        if terr:
            boundary = self._boundaries.get(terr.id)
            if boundary:
                if self._edit_base_vertices is not None:
                    if self._insert_anchor_index is not None:
                        preview = self._spliced_vertices(self._inserted_points + [preview_pos])
                        boundary.set_points(preview)
                    # else: anchor not grabbed yet — nothing to preview,
                    # the original shape stays as-is.
                else:
                    boundary.set_points(points + [preview_pos], self._current_curve_controls())
        if self._neon_overlay:
            self._neon_overlay.set_chain(self._neon_chain(preview_pos))
        if self._alignment_guides:
            self._alignment_guides.update(preview_pos, self._all_current_vertices())
        self._l.freehand_badge.set_measurement(distance_m, angle_deg)

    def _on_freehand_finished(self):
        self._freehand_badge_timer.stop()
        self._l.freehand_badge.hide()
        if self._neon_overlay:
            self._neon_overlay.remove()
            self._neon_overlay = None
        if self._vertex_handles:
            self._vertex_handles.remove()
            self._vertex_handles = None
        if self._alignment_guides:
            self._alignment_guides.remove()
            self._alignment_guides = None
        tool = self._l.canvas.engine._terrain_freehand_tool
        raw_points = tool.points
        raw_curve_controls = tool.curve_controls
        tool.on_curve_changed = None
        tool.on_preview_changed = None
        tool.on_point_moved = None
        tool.on_escape = None
        tool.deactivate()
        if self._prev_tool_name:
            self._l.canvas.engine.tool_manager.activate(self._prev_tool_name)
            self._prev_tool_name = None

        terr = self._current_terrain()
        if not terr:
            self._reset_freehand_edit_state()
            return
        boundary = self._boundaries.get(terr.id)

        final_curve_controls: dict[int, QPointF] = {}
        if self._edit_base_vertices is not None and self._insert_anchor_index is not None and self._inserted_points:
            final_points = self._spliced_vertices(self._inserted_points)
            # Insert-mode restructures the vertex list, so any curves the
            # base shape had (indices computed against the OLD list) no
            # longer point at the right segments — dropped rather than
            # risk bowing the wrong edge.
        elif self._edit_base_vertices is None:
            final_points = raw_points
            final_curve_controls = raw_curve_controls
        else:
            final_points = None  # anchor grabbed but nothing inserted — nothing changed

        if final_points and len(final_points) >= 3:
            terr.shape = "freehand"
            terr.points = [(p.x(), p.y()) for p in final_points]
            terr.curve_controls = {i: (p.x(), p.y()) for i, p in final_curve_controls.items()}
            xs = [p.x() for p in final_points]
            ys = [p.y() for p in final_points]
            terr.width = max(1, int(max(xs) - min(xs)))
            terr.height = max(1, int(max(ys) - min(ys)))
            if boundary:
                boundary.set_points(final_points, final_curve_controls)
            self._maybe_persist(
                terr, shape="freehand", width=terr.width, height=terr.height,
                points_json=json.dumps(terr.points),
                curve_controls_json=json.dumps({str(k): v for k, v in terr.curve_controls.items()}),
            )
        else:
            # Too few points to form a real shape (or nothing was actually
            # inserted) — revert to whatever this terreno's boundary
            # looked like before "Livre" was clicked (terr.shape was never
            # touched, since that only happens on a successful finish
            # above).
            if boundary:
                boundary.update_shape(terr.shape)
            self._l.terrain_edit_panel.set_shape(terr.shape)
        self._reset_freehand_edit_state()
        self._l.canvas.engine._update_grid()

    def _reset_freehand_edit_state(self):
        self._edit_base_vertices = None
        self._insert_anchor_index = None
        self._inserted_points = []

    def _cancel_freehand_if_active(self):
        """Discards an in-progress "Livre" drawing outright (not even the
        placed-so-far points) — used when the edit panel closes, or a
        different terreno is opened, while drawing is still armed."""
        if not self._freehand_badge_timer.isActive():
            return
        self._freehand_badge_timer.stop()
        self._l.freehand_badge.hide()
        if self._neon_overlay:
            self._neon_overlay.remove()
            self._neon_overlay = None
        if self._vertex_handles:
            self._vertex_handles.remove()
            self._vertex_handles = None
        if self._alignment_guides:
            self._alignment_guides.remove()
            self._alignment_guides = None
        tool = self._l.canvas.engine._terrain_freehand_tool
        tool.on_preview_changed = None
        tool.on_point_moved = None
        tool.on_curve_changed = None
        tool.on_escape = None
        tool.deactivate()
        if self._prev_tool_name:
            self._l.canvas.engine.tool_manager.activate(self._prev_tool_name)
            self._prev_tool_name = None
        self._l.terrain_edit_panel.cancel_freehand()
        terr = self._current_terrain()
        if terr:
            boundary = self._boundaries.get(terr.id)
            if boundary:
                boundary.update_shape(terr.shape)
        self._reset_freehand_edit_state()

    def _update_freehand_badge_pos(self):
        pos = self._l.mapFromGlobal(QCursor.pos())
        self._l.freehand_badge.move(pos.x() + 16, pos.y() + 16)
        self._l.freehand_badge.raise_()

    def on_add_requested(self):
        terrain_id = str(uuid.uuid4())
        color = self._next_palette_color()
        name = f"Terreno {len(self._terrains) + 1}"

        terr = _Terrain(id=terrain_id, name=name, shape=self.DEFAULT_SHAPE,
                         width=self.DEFAULT_WIDTH, height=self.DEFAULT_HEIGHT, color=color)
        self._terrains[terrain_id] = terr
        self._active_id = terrain_id
        self._is_creating = True

        scene = self._l.canvas.engine.viewport.scene()
        boundary = MapBoundary(scene, color)
        boundary.set_on_position_changed(lambda pos, tid=terrain_id: self._on_boundary_moved(tid, pos))
        if not self._l.terrain_panel.is_infinite:
            boundary.show(terr.width, terr.height, terr.shape)
            view_center = self._l.canvas.engine.viewport.mapToScene(
                self._l.canvas.engine.viewport.viewport().rect().center()
            )
            boundary.set_position(view_center + self._stagger_offset())
        self._boundaries[terrain_id] = boundary
        self._l.canvas.engine._brush_tool.set_active_boundary(boundary)
        self._sync_all_boundaries()

        panel = self._l.terrain_edit_panel
        panel.load(terr.name, terr.shape, terr.width, terr.height, terr.color, None)
        panel.set_min_dimensions(16, 16)
        panel.set_create_mode(True)
        panel.show()
        panel.raise_()
        self._l.terrain_panel.set_new_button_enabled(False)
        self._l._reposition()

    def on_save_requested(self):
        if not self._is_creating:
            return
        terr = self._current_terrain()
        if terr is None:
            return
        photo = self._load_photo(terr.image_path)
        is_first = len(self._terrains) == 1
        self._l.terrain_panel.add_terrain_card(
            terr.id, terr.name, terr.color,
            area_m2=self._area_m2(terr), object_count=self._count_objects_in(terr),
            photo=photo,
        )
        self._persist_create(terr)
        self._is_creating = False
        self.on_close_edit()
        # Se o mapa estava infinito, desmarca automaticamente ao criar
        # o primeiro terreno — o terreno recém-criado fica imediatamente ativo.
        if self._l.terrain_panel.is_infinite:
            self._l.terrain_panel.set_infinite(False)
        if is_first:
            self._l.terrain_panel.select_terrain(terr.id)

    def on_edit_requested(self, terrain_id: str):
        """"Editar" from a card's "..." menu — reopens the same sub painel,
        pre-filled; from here on, field edits auto-persist (see
        _maybe_persist) instead of needing another "Salvar"."""
        self._cancel_freehand_if_active()
        terr = self._terrains.get(terrain_id)
        if terr is None:
            return
        self._active_id = terrain_id
        self._is_creating = False
        panel = self._l.terrain_edit_panel
        photo = self._load_photo(terr.image_path)
        panel.load(terr.name, terr.shape, terr.width, terr.height, terr.color, photo)
        panel.set_create_mode(False)
        panel.show()
        panel.raise_()
        self._l.terrain_panel.set_new_button_enabled(False)
        self._l._reposition()
        boundary = self._boundaries.get(terrain_id)
        if boundary and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(boundary)

    def on_close_edit(self):
        self._cancel_freehand_if_active()
        if self._is_creating:
            # Closed without ever clicking "Salvar" — discard the
            # in-progress terreno's boundary/entry instead of leaving an
            # orphaned one that isn't in the list and was never persisted.
            terr = self._current_terrain()
            if terr:
                boundary = self._boundaries.pop(terr.id, None)
                if boundary:
                    boundary.hide()
                self._terrains.pop(terr.id, None)
            self._is_creating = False
        self._active_id = None
        self._l.terrain_edit_panel.hide()
        self._l.terrain_panel.set_new_button_enabled(True)
        # Re-sync the brush's active boundary to whatever's still selected
        # in the card list (not unconditionally None) — this also fires
        # when Terrain itself closes (_on_terrain_panel_hidden), which must
        # not clobber a boundary target picked from Brush's own "pintando
        # em" dropdown independently of this panel.
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(self._boundaries.get(sel_id))
        self._sync_all_boundaries()
        self._l._reposition()

    # ─── Edit panel field handlers ───

    def _current_terrain(self) -> _Terrain | None:
        return self._terrains.get(self._active_id) if self._active_id else None

    def _maybe_persist(self, terr: _Terrain, **fields):
        """Auto-persists a field change straight away — but only once the
        terreno is a real, saved row (mid-creation edits live purely on the
        in-memory _Terrain + preview boundary until "Salvar Terreno")."""
        if self._uow and not self._is_creating:
            self._uow.terrains.update(terr.id, **fields)

    def _on_name_changed(self, name: str):
        terr = self._current_terrain()
        if not terr or not name:
            return
        terr.name = name
        card = self._l.terrain_panel.get_card(terr.id)
        if card:
            card.set_name(name)
        self._maybe_persist(terr, name=name)

    def _on_shape_changed(self, shape: str):
        terr = self._current_terrain()
        if not terr:
            return
        terr.shape = shape
        boundary = self._boundaries.get(terr.id)
        if boundary:
            boundary.update_shape(shape)
        self._maybe_persist(terr, shape=shape)
        self._l.canvas.engine._update_grid()

    def _on_dims_changed(self, width: int, height: int):
        terr = self._current_terrain()
        if not terr:
            return
        terr.width, terr.height = width, height
        boundary = self._boundaries.get(terr.id)
        if boundary:
            boundary.update_dimensions(width, height)
        self._maybe_persist(terr, width=width, height=height)
        self._l.canvas.engine._update_grid()

    def _on_color_changed(self, color: QColor):
        terr = self._current_terrain()
        if not terr:
            return
        terr.color = QColor(color)
        boundary = self._boundaries.get(terr.id)
        if boundary:
            boundary.set_color(terr.color)
        card = self._l.terrain_panel.get_card(terr.id)
        if card:
            card.set_color(terr.color)
        self._maybe_persist(terr, color=terr.color.name())

    def _project_dir(self):
        window = self._l.window()
        return window.project.path if window and getattr(window, "project", None) else None

    def _load_photo(self, image_path: str) -> QPixmap | None:
        if not image_path:
            return None
        pixmap = QPixmap(resolve_asset_path(self._project_dir(), image_path))
        return pixmap if not pixmap.isNull() else None

    def _on_image_changed(self, path: str):
        terr = self._current_terrain()
        if not terr:
            return
        stored_path = import_asset(self._project_dir(), path, "assets/terrains", terr.id)
        terr.image_path = stored_path
        photo = self._load_photo(stored_path)
        card = self._l.terrain_panel.get_card(terr.id)
        if card:
            card.set_photo(photo)
        self._l.terrain_edit_panel.set_image(photo)
        self._maybe_persist(terr, image_path=stored_path)

    # ─── Stats (área/objetos shown on the card) ───

    def _area_m2(self, terr: _Terrain) -> float:
        if terr.shape == "freehand" and len(terr.points) >= 3:
            # Shoelace formula — the bounding-box width*height used for
            # every parametric shape would badly overstate an irregular
            # click-placed polygon's actual area. Uses the straight-edge
            # vertex polygon even where a segment is curved (terr.
            # curve_controls) — the bulge's contribution is small and not
            # worth the added complexity of integrating along a Bézier
            # edge just for this display figure.
            pts = terr.points
            total = 0.0
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                total += x1 * y2 - x2 * y1
            return abs(total) / 2.0
        return float(terr.width * terr.height)

    def _count_objects_in(self, terr: _Terrain) -> int:
        """Heuristic: stamped/generated assets sit at zValue >= 10, above
        terrain (1) and zones (5) — count scene items at that tier whose
        position falls inside this terreno's boundary shape. Same idea as
        RegionMediator._count_objects_in."""
        boundary = self._boundaries.get(terr.id)
        if not boundary:
            return 0
        count = 0
        for item in self._l.canvas.engine.viewport.scene().items():
            if item.zValue() < 10:
                continue
            if boundary.contains_point(item.scenePos()):
                count += 1
        return count

    # ─── Persistence helpers ───

    def _next_palette_color(self) -> QColor:
        return self._l.terrain_panel.next_palette_color()

    def _terrain_name_options(self) -> list[tuple[str, str]]:
        return [(tid, terr.name) for tid, terr in self._terrains.items()]

    def _persist_create(self, terr: _Terrain):
        if not self._uow:
            return
        boundary = self._boundaries.get(terr.id)
        pos = boundary.position if boundary else QPointF(0, 0)
        self._uow.terrains.create(
            id=terr.id, map_id=self.MAP_ID, name=terr.name, shape=terr.shape,
            width=terr.width, height=terr.height, color=terr.color.name(),
            position_x=pos.x(), position_y=pos.y(),
            visible=int(boundary.visible if boundary else False),
            image_path=terr.image_path, points_json=json.dumps(terr.points),
            curve_controls_json=json.dumps({str(k): v for k, v in terr.curve_controls.items()}),
        )
