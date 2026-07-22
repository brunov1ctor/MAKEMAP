"""ParallaxPresetSection — collapsible header + per-layer parameter rows for
one parallax preset, shown in the Config panel's Parallax group.
"""

from __future__ import annotations

import json
import os
import re

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QWidget,
    QFileDialog, QLineEdit, QStackedWidget, QCheckBox, QTextEdit, QComboBox,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QTimer
from PySide6.QtGui import QPixmap, QImage

from src.styles.tokens import Colors
from src.layouts.panels.stepper import NumberStepper
from src.engines.map.parallax import get_parallax_library, LayerEffect, EFFECT_KINDS, EFFECT_DEFAULTS

_EFFECT_LABELS = dict(EFFECT_KINDS)

# Shown on each effect's checkbox — none of the 4 kinds had any explanation
# in the UI itself before (only the JSON-template help text documented
# them, invisible unless that panel happened to be open), which is exactly
# why "tingir cor" read as unclear to a user just clicking through the
# per-layer effects list.
_EFFECT_TOOLTIPS = {
    "tint": "Tinge a camada com a Cor escolhida, na intensidade de Força — 0% não altera nada, 100% substitui a cor original inteiramente.",
    "blur": "Desfoca a camada (efeito de profundidade/distância) — Raio maior = mais desfocado.",
    "chromatic": "Aberração cromática: separa levemente as cores (vermelho/ciano) nas bordas, como uma lente com distorção óptica — Desloc. maior = franja mais visível.",
    "wave": "Ondula a camada horizontalmente ao longo do tempo — Amplit. controla o quanto desloca, Freq. quantas ondas cabem na imagem, Veloc. a rapidez da animação.",
}

_IMG_FILTER = "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"


def _has_transparency(image_path: str) -> bool:
    """Whether the image actually has any translucent/transparent pixel —
    parallax layers need this to composite over the ones behind them, so a
    flat opaque image is worth flagging before it silently blocks the view."""
    img = QImage(image_path)
    if img.isNull() or not img.hasAlphaChannel():
        return False
    # Downscale first — checking every pixel of a full-res image per row
    # rebuild would be wasteful; a small sample is enough to detect alpha use.
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    small = small.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(small.height()):
        for x in range(small.width()):
            if small.pixelColor(x, y).alpha() < 250:
                return True
    return False


def _reorder_hides_layer(layers, source_index: int, target_index: int) -> bool:
    """Would moving `source_index` to `target_index` place a transparent
    layer behind an opaque one, or an opaque one in front of a
    transparent one? Lower list index = drawn first = further back (see
    ParallaxLayer.order / Viewport.drawBackground's paint loop) — a
    no-alpha layer fully covers whatever was painted before it, so any
    layer sitting behind one (at a lower index) becomes invisible. Used
    to reject drags that would silently hide a layer instead of letting
    it happen and leaving the user hunting for why an effect vanished
    (the "sem alfa" badge/tooltip on each row already warns about this,
    but doesn't stop it)."""
    n = len(layers)
    if not (0 <= source_index < n) or not (0 <= target_index < n) or source_index == target_index:
        return False
    order = list(layers)
    order.insert(target_index, order.pop(source_index))
    opaque_indices = [i for i, l in enumerate(order) if not _has_transparency(l.image_path)]
    transparent_indices = [i for i, l in enumerate(order) if _has_transparency(l.image_path)]
    if not opaque_indices or not transparent_indices:
        return False  # nothing to protect either way
    return max(opaque_indices) > min(transparent_indices)


def _divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line


def _parse_layers_json(text: str) -> list[dict]:
    """Permissive parser for the layer-config snippets users paste in —
    typically a bare list of JS-style object literals (unquoted keys, no
    enclosing brackets, trailing commas), not strict JSON. Raises ValueError
    with a Portuguese message on anything unparseable."""
    # Strip "// ..." line comments — the template ships with them to explain
    # each field, and users are expected to leave them in place while editing.
    text = re.sub(r'//[^\n]*', '', text)
    text = text.strip()
    if not text:
        raise ValueError("Cole um JSON com pelo menos uma camada.")
    if not text.startswith("["):
        text = f"[{text}]"
    # Quote bare identifier keys: { name: ... } -> { "name": ... }
    text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    # Drop trailing commas before a closing bracket/brace.
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ValueError("Esperava uma lista de camadas (array).")
    return data


# Motion/tile modes as (key, label) pairs — driving the dropdowns in
# _build_layer_row from these lists (instead of one-off hardcoded widgets)
# means adding a new mode later is a one-line addition here, plus the
# matching render branch in Viewport._draw_parallax_layer.
_MOTION_MODES = [("scroll", "Scroll"), ("orbit", "Órbita")]
_TILE_MODES = [("repeat", "Repetir"), ("mirror", "Espelhar"), ("fade", "Fade")]

# camelCase JSON key -> ParallaxLayer field name, plus how to cast it.
# Accepts both camelCase (what users typically paste) and snake_case
# (what get_preset()/save() actually use) for every field.
_JSON_FLOAT_FIELDS = {
    "speedX": "speed_x", "speed_x": "speed_x",
    "speedY": "speed_y", "speed_y": "speed_y",
    "opacity": "opacity",
    "orbitRadius": "orbit_radius", "orbit_radius": "orbit_radius",
    "orbitPeriod": "orbit_period", "orbit_period": "orbit_period",
    "opacityMin": "opacity_min", "opacity_min": "opacity_min",
    "opacityMax": "opacity_max", "opacity_max": "opacity_max",
    "opacityPeriod": "opacity_period", "opacity_period": "opacity_period",
    "scaleMin": "scale_min", "scale_min": "scale_min",
    "scaleMax": "scale_max", "scale_max": "scale_max",
    "scalePeriod": "scale_period", "scale_period": "scale_period",
    "rotationAmplitude": "rotation_amplitude", "rotation_amplitude": "rotation_amplitude",
    "rotationPeriod": "rotation_period", "rotation_period": "rotation_period",
}
_JSON_BOOL_FIELDS = {
    "opacityPulse": "opacity_pulse", "opacity_pulse": "opacity_pulse",
    "scalePulse": "scale_pulse", "scale_pulse": "scale_pulse",
    "rotationPulse": "rotation_pulse", "rotation_pulse": "rotation_pulse",
}
_JSON_STR_FIELDS = {
    "name": "name",
    "motionMode": "motion_mode", "motion_mode": "motion_mode",
    "tileMode": "tile_mode", "tile_mode": "tile_mode",
}

# (json key shown in the template, explanation) — rendered as "// key: doc"
# comment lines above the pasted layers, so the field meanings travel with
# the JSON itself instead of living only in this file.
_JSON_PARAM_DOCS = [
    ("name", "nome da camada (só identificação, não afeta o desenho)"),
    ("speedX / speedY", "velocidade horizontal/vertical ligada ao pan — 0 = fixa na tela; negativo = anda ao contrário do pan"),
    ("opacity", "opacidade da camada, de 0 a 1"),
    ("motionMode", '"scroll" (ladrilhada, rola com o pan) ou "orbit" (presa, balança num raio curto sem atravessar a tela)'),
    ("tileMode", 'como as cópias se encontram na costura — só usado com motionMode "scroll": "repeat" | "mirror" | "fade"'),
    ("orbitRadius", 'raio do balanço em pixels de tela — só usado com motionMode "orbit"'),
    ("orbitPeriod", "segundos para uma volta completa da órbita"),
    ("opacityPulse", "liga (true) ou desliga (false) a opacidade oscilando sozinha com o tempo"),
    ("opacityMin / opacityMax", (
        'faixa (0 a 1) que MULTIPLICA a opacidade base ("opacity" acima), quando opacityPulse é true — '
        'não é um valor absoluto. Ex.: opacity 0.8 + opacityMin 0.6/opacityMax 1.0 oscila entre 0.48 e 0.8'
    )),
    ("opacityPeriod", "segundos por ciclo completo da oscilação de opacidade"),
    ("scalePulse", "liga/desliga a escala oscilando sozinha com o tempo"),
    ("scaleMin / scaleMax", "faixa em % dentro da qual a escala oscila, quando scalePulse é true"),
    ("scalePeriod", "segundos por ciclo completo da oscilação de escala"),
    ("rotationPulse", "liga/desliga uma leve rotação oscilando sozinha com o tempo"),
    ("rotationAmplitude", "graus para cada lado que a rotação oscila (-amp..+amp)"),
    ("rotationPeriod", "segundos por ciclo completo da oscilação de rotação"),
    ("effects", (
        'lista de efeitos visuais (shaders leves), cada um: { kind: "...", enabled: true, params: {...} }. '
        'kinds disponíveis — tint: {color, strength} tinge a camada; blur: {radius} desfoca; '
        'chromatic: {offset_px} aberração cromática; wave: {amplitude, frequency, speed} distorce em ondas (anima com o tempo)'
    )),
]


class ParallaxPresetSection(QFrame):
    """One preset: collapsible header (rename/add-layer/delete) + a param
    row per layer (thumbnail, speed, opacity, stacking order, delete)."""

    delete_requested = Signal(str)  # preset_key
    reorder_requested = Signal(str, str)  # from_preset_key, to_preset_key

    def __init__(self, preset_key: str, name: str, parent=None):
        super().__init__(parent)
        self.preset_key = preset_key
        self._expanded = True
        self._drop_target = False
        self._is_parallax_preset_section = True
        self.setStyleSheet("background: transparent;")

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        # Without this, collapsing the layer list (hiding self._content)
        # leaves the section's parent layout holding a stale, too-tall slot
        # for a moment — and QVBoxLayout, with no stretch and nothing left
        # to fill it, centers the lone visible header inside that leftover
        # space instead of pinning it to the top, which reads as a gap
        # between this card's header and whatever comes above it.
        main.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ─── Header ───
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setStyleSheet(self._header_style())
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(4)

        # ─── Drag handle: reorders the whole preset relative to its
        # siblings — same GhostCard/hover-highlight pattern the layer rows
        # below already use, just one level up — ghost grabs the header
        # only (not the whole card, which can be tall with many layers).
        self._drag_handle = QLabel("⠿")
        self._drag_handle.setFixedWidth(16)
        self._drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_handle.setToolTip("Arraste para reordenar este preset")
        self._drag_handle.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        self._setup_preset_drag(self._drag_handle)
        h_lay.addWidget(self._drag_handle)

        self._arrow = QToolButton()
        self._arrow.setText("▼")
        self._arrow.setFixedWidth(16)
        self._arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow.setStyleSheet(
            f"QToolButton {{ border: none; color: {Colors.ACCENT}; font-size: 8px; background: transparent; }}"
        )
        self._arrow.clicked.connect(self._toggle)
        h_lay.addWidget(self._arrow)

        self._name_stack = QStackedWidget()
        self._name_stack.setStyleSheet("background: transparent; border: none;")
        self._name_stack.setFixedHeight(22)
        self._title_label = QLabel(name)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; background: transparent; border: none;"
        )
        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 9pt;
                background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                border-radius: 3px; padding: 0 4px;
            }}
        """)
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.editingFinished.connect(self._finish_rename)
        self._name_stack.addWidget(self._title_label)
        self._name_stack.addWidget(self._name_edit)
        h_lay.addWidget(self._name_stack)

        rename_btn = QToolButton()
        rename_btn.setText("✎")
        rename_btn.setFixedSize(18, 18)
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.setStyleSheet(
            f"QToolButton {{ border: none; font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        rename_btn.clicked.connect(self._start_rename)
        h_lay.addWidget(rename_btn)

        self._count_lbl = QLabel("(0)")
        self._count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        h_lay.addWidget(self._count_lbl)
        h_lay.addStretch()

        add_layer_btn = QToolButton()
        add_layer_btn.setText("+ Camada")
        add_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_layer_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; padding: 2px 6px; "
            f"color: {Colors.ACCENT}; font-size: 9px; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_layer_btn.clicked.connect(self._on_add_layer)
        h_lay.addWidget(add_layer_btn)

        json_btn = QToolButton()
        json_btn.setText("{ } JSON")
        json_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        json_btn.setToolTip("Colar/editar várias camadas de uma vez em JSON")
        json_btn.setStyleSheet(
            f"QToolButton {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE}; "
            f"padding: 2px 6px; color: {Colors.TEXT_SECONDARY}; font-size: 9px; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}"
        )
        json_btn.clicked.connect(self._toggle_json_import)
        h_lay.addWidget(json_btn)

        del_btn = QToolButton()
        del_btn.setText("🗑")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Excluir preset")
        del_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.preset_key))
        h_lay.addWidget(del_btn)

        main.addWidget(self._header)

        # ─── JSON bulk import (collapsed by default) ───
        self._json_widget = QFrame()
        self._json_widget.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.02); border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        json_lay = QVBoxLayout(self._json_widget)
        json_lay.setContentsMargins(10, 8, 10, 8)
        json_lay.setSpacing(6)

        json_hint = QLabel(
            "Cole ou edite as camadas em JSON (name, speedX, speedY, opacity). "
            "Aplica na ordem às camadas já existentes neste preset."
        )
        json_hint.setWordWrap(True)
        json_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        json_lay.addWidget(json_hint)

        self._json_edit = QTextEdit()
        self._json_edit.setFixedHeight(120)
        self._json_edit.setStyleSheet(f"""
            QTextEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 8pt; font-family: Consolas, monospace;
                background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                padding: 4px;
            }}
        """)
        json_lay.addWidget(self._json_edit)

        self._json_error_lbl = QLabel("")
        self._json_error_lbl.setWordWrap(True)
        self._json_error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 8pt; background: transparent; border: none;")
        self._json_error_lbl.hide()
        json_lay.addWidget(self._json_error_lbl)

        json_btn_row = QHBoxLayout()
        json_btn_row.setSpacing(6)
        json_btn_row.addStretch()

        json_cancel_btn = QToolButton()
        json_cancel_btn.setText("Cancelar")
        json_cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        json_cancel_btn.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 10px; font-size: 8pt; "
            f"color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.08); }}"
        )
        json_cancel_btn.clicked.connect(self._toggle_json_import)
        json_btn_row.addWidget(json_cancel_btn)

        json_apply_btn = QToolButton()
        json_apply_btn.setText("Aplicar")
        json_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        json_apply_btn.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 12px; font-size: 8pt; font-weight: bold; "
            f"color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        json_apply_btn.clicked.connect(self._apply_json_import)
        json_btn_row.addWidget(json_apply_btn)

        json_lay.addLayout(json_btn_row)

        self._json_widget.hide()
        main.addWidget(self._json_widget)

        # ─── Content (layer rows) ───
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(8, 6, 8, 6)
        self._content_lay.setSpacing(6)
        main.addWidget(self._content)

        self._refresh_layers()

    def _header_style(self, drop_target: bool = False) -> str:
        border = Colors.ACCENT if drop_target else Colors.BORDER_SUBTLE
        bg = "rgba(79,195,247,0.15)" if drop_target else "rgba(255,255,255,0.02)"
        return f"QFrame {{ background: {bg}; border: none; border-bottom: 1px solid {border}; }}"

    def _set_drop_target(self, on: bool):
        self._drop_target = on
        self._header.setStyleSheet(self._header_style(on))

    @staticmethod
    def _preset_section_at_global_pos(global_pos):
        from PySide6.QtWidgets import QApplication
        w = QApplication.widgetAt(global_pos)
        while w is not None:
            if getattr(w, "_is_parallax_preset_section", False):
                return w
            w = w.parentWidget()
        return None

    def _setup_preset_drag(self, handle: QLabel):
        """Same press/move/release ghost-drag pattern as _build_layer_row's
        handle, one level up: dragging this reorders the whole preset among
        its siblings in the Config panel's list, instead of a layer inside it."""
        drag_state = {"start": None, "ghost": None, "hover_section": None}

        def _find_scroll_host() -> QWidget:
            from PySide6.QtWidgets import QScrollArea
            w = self.parent()
            while w:
                if isinstance(w, QScrollArea):
                    return w.viewport()
                if w.parent() is None:
                    return w
                w = w.parent()
            return self

        def _clear_hover_highlight():
            hover_section = drag_state["hover_section"]
            if hover_section is not None:
                hover_section._set_drop_target(False)
                drag_state["hover_section"] = None

        def _handle_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                drag_state["start"] = event.pos()

        def _handle_move(event):
            start = drag_state["start"]
            if start is None:
                return
            if drag_state["ghost"] is None:
                if (event.pos() - start).manhattanLength() <= 6:
                    return
                from src.layouts.panels.assets.card import GhostCard
                host = _find_scroll_host()
                drag_state["ghost"] = GhostCard(self._header, host)

            ghost = drag_state["ghost"]
            global_pos = event.globalPosition().toPoint()
            offset_in_header = handle.mapTo(self._header, start)
            ghost.move_to(global_pos, offset_in_header)

            target = self._preset_section_at_global_pos(global_pos)
            if target is not drag_state["hover_section"]:
                _clear_hover_highlight()
                if target is not None and target is not self:
                    target._set_drop_target(True)
                    drag_state["hover_section"] = target

        def _handle_release(event):
            ghost = drag_state["ghost"]
            if ghost is not None:
                ghost.hide()
                ghost.deleteLater()
                target = self._preset_section_at_global_pos(event.globalPosition().toPoint())
                _clear_hover_highlight()
                if target is not None and target is not self:
                    self.reorder_requested.emit(self.preset_key, target.preset_key)
            drag_state["start"] = None
            drag_state["ghost"] = None

        handle.mousePressEvent = _handle_press
        handle.mouseMoveEvent = _handle_move
        handle.mouseReleaseEvent = _handle_release

    def _find_scroll_area(self):
        """Walks up to the enclosing QScrollArea (the Config panel's own,
        several levels up) — used by _toggle to keep this card's header
        pinned at the same on-screen spot across expand/collapse, instead
        of the whole list jumping when this card's height changes."""
        from PySide6.QtWidgets import QScrollArea
        w = self.parent()
        while w is not None:
            if isinstance(w, QScrollArea):
                return w
            w = w.parent()
        return None

    def _toggle(self):
        scroll_area = self._find_scroll_area()
        old_viewport_y = self.mapTo(scroll_area.viewport(), QPoint(0, 0)).y() if scroll_area else None

        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")

        if scroll_area is not None:
            def _restore_scroll():
                # Absolute, not relative: collapsing/expanding shrinks or
                # grows the total scrollable height, which can silently
                # clamp the scrollbar's value on its own — computing the
                # target value from scratch (this card's fixed position
                # inside the scrolled content minus where we want its top
                # to land in the viewport) is robust to that, where
                # "current value + delta" was not.
                content_y = self.mapTo(scroll_area.widget(), QPoint(0, 0)).y()
                scroll_area.verticalScrollBar().setValue(content_y - old_viewport_y)
            # Deferred: hide()/show() doesn't resettle the layout
            # synchronously, so measuring the new position right away would
            # still read the stale (pre-toggle) geometry.
            QTimer.singleShot(0, _restore_scroll)

    def _start_rename(self):
        self._name_edit.setText(self._title_label.text())
        self._name_stack.setCurrentIndex(1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _finish_rename(self):
        if self._name_stack.currentIndex() != 1:
            return
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._title_label.text():
            self._title_label.setText(new_name)
            get_parallax_library().rename_preset(self.preset_key, new_name)
        self._name_stack.setCurrentIndex(0)

    def _on_add_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem da camada", "", _IMG_FILTER)
        if not path:
            return
        get_parallax_library().add_layer(self.preset_key, path)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _refresh_json_template_if_open(self):
        """Keep the JSON textbox in sync with the layer list — otherwise
        adding/removing a layer while the panel is open leaves it editing a
        stale set of rows that no longer matches what's on screen."""
        if not self._json_widget.isHidden():
            self._json_edit.setPlainText(self._build_json_template())
            self._json_error_lbl.hide()

    def _build_json_template(self) -> str:
        preset = get_parallax_library().get_preset(self.preset_key)
        layers = preset.layers if preset else []
        if not layers:
            # Nothing to attach params to yet — a single zeroed/default row
            # the user can duplicate once they've added images.
            layers = [None]

        def _row_text(i: int, l) -> str:
            name = (l.name if l else None) or f"camada_{i+1}"
            speed_x = l.speed_x if l else 0.0
            speed_y = l.speed_y if l else 0.0
            opacity = l.opacity if l else 1.0
            motion_mode = l.motion_mode if l else "scroll"
            tile_mode = l.tile_mode if l else "repeat"
            orbit_radius = l.orbit_radius if l else 20.0
            orbit_period = l.orbit_period if l else 8.0
            opacity_pulse = str(l.opacity_pulse if l else False).lower()
            opacity_min = l.opacity_min if l else 0.6
            opacity_max = l.opacity_max if l else 1.0
            opacity_period = l.opacity_period if l else 4.0
            scale_pulse = str(l.scale_pulse if l else False).lower()
            scale_min = l.scale_min if l else 100.0
            scale_max = l.scale_max if l else 110.0
            scale_period = l.scale_period if l else 6.0
            rotation_pulse = str(l.rotation_pulse if l else False).lower()
            rotation_amplitude = l.rotation_amplitude if l else 2.0
            rotation_period = l.rotation_period if l else 10.0
            effects_json = ", ".join(
                f'{{ kind: "{e.kind}", enabled: {str(e.enabled).lower()}, params: {json.dumps(e.params)} }}'
                for e in (l.effects if l else [])
            )
            return (
                f'  {{\n'
                f'    name: "{name}", speedX: {speed_x}, speedY: {speed_y}, opacity: {opacity},\n'
                f'    motionMode: "{motion_mode}", tileMode: "{tile_mode}",\n'
                f'    orbitRadius: {orbit_radius}, orbitPeriod: {orbit_period},\n'
                f'    opacityPulse: {opacity_pulse}, opacityMin: {opacity_min}, opacityMax: {opacity_max}, opacityPeriod: {opacity_period},\n'
                f'    scalePulse: {scale_pulse}, scaleMin: {scale_min}, scaleMax: {scale_max}, scalePeriod: {scale_period},\n'
                f'    rotationPulse: {rotation_pulse}, rotationAmplitude: {rotation_amplitude}, rotationPeriod: {rotation_period},\n'
                f'    effects: [{effects_json}]\n'
                f'  }}'
            )

        comment_lines = "\n".join(f"// {key}: {doc}" for key, doc in _JSON_PARAM_DOCS)
        rows_text = ",\n".join(_row_text(i, l) for i, l in enumerate(layers))
        return f"{comment_lines}\n[\n{rows_text}\n]"

    def _toggle_json_import(self):
        opening = self._json_widget.isHidden()
        if opening:
            self._json_edit.setPlainText(self._build_json_template())
            self._json_error_lbl.hide()
        self._json_widget.setVisible(opening)

    def _apply_json_import(self):
        try:
            rows = _parse_layers_json(self._json_edit.toPlainText())
        except ValueError as exc:
            self._json_error_lbl.setText(str(exc))
            self._json_error_lbl.show()
            return

        preset = get_parallax_library().get_preset(self.preset_key)
        layers = preset.layers if preset else []
        if not layers:
            self._json_error_lbl.setText("Adicione as imagens das camadas primeiro (botão + Camada) antes de aplicar o JSON.")
            self._json_error_lbl.show()
            return

        applied = 0
        for index, row in enumerate(rows):
            if index >= len(layers):
                break
            if not isinstance(row, dict):
                continue
            kwargs = {}
            for json_key, value in row.items():
                if json_key in _JSON_FLOAT_FIELDS:
                    kwargs[_JSON_FLOAT_FIELDS[json_key]] = float(value)
                elif json_key in _JSON_BOOL_FIELDS:
                    kwargs[_JSON_BOOL_FIELDS[json_key]] = bool(value)
                elif json_key in _JSON_STR_FIELDS:
                    kwargs[_JSON_STR_FIELDS[json_key]] = str(value)
                elif json_key == "effects" and isinstance(value, list):
                    kwargs["effects"] = [
                        LayerEffect(
                            kind=str(e.get("kind", "")),
                            enabled=bool(e.get("enabled", True)),
                            params=e.get("params") if isinstance(e.get("params"), dict) else {},
                        )
                        for e in value
                        if isinstance(e, dict) and e.get("kind")
                    ]
            if kwargs:
                get_parallax_library().update_layer(self.preset_key, index, **kwargs)
                applied += 1

        self._refresh_layers()
        if applied < len(rows):
            self._json_error_lbl.setText(
                f"Aviso: {applied} de {len(rows)} camadas do JSON foram aplicadas "
                f"(há apenas {len(layers)} camada(s) neste preset)."
            )
            self._json_error_lbl.show()
        else:
            self._json_error_lbl.hide()
            self._json_widget.hide()

    def _refresh_layers(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        preset = get_parallax_library().get_preset(self.preset_key)
        layers = preset.layers if preset else []
        self._count_lbl.setText(f"({len(layers)})")

        for index, layer in enumerate(layers):
            self._content_lay.addWidget(self._build_layer_row(index, layer))

    def _row_style(self, drop_target: bool = False) -> str:
        border = Colors.ACCENT if drop_target else Colors.BORDER_SUBTLE
        bg = "rgba(79,195,247,0.10)" if drop_target else "rgba(255,255,255,0.03)"
        style = f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
        if not drop_target:
            # Hover highlight — skipped while this row is an active drag
            # target, which already has its own (stronger) highlight above.
            style += f"QFrame:hover {{ background: rgba(79,195,247,0.06); border-color: {Colors.ACCENT}; }}"
        return style

    def _row_at_global_pos(self, global_pos) -> QFrame | None:
        """Which layer row (if any) is under a global point — walks up from
        whatever widget is actually there, since the cursor may be over a
        child label/stepper inside the row, not the row frame itself."""
        from PySide6.QtWidgets import QApplication
        w = QApplication.widgetAt(global_pos)
        while w is not None:
            if getattr(w, "_is_parallax_layer_row", False):
                return w
            w = w.parentWidget()
        return None

    def _build_layer_row(self, index: int, layer) -> QWidget:
        row = QFrame()
        row.setStyleSheet(self._row_style())
        row._is_parallax_layer_row = True
        row._layer_index = index
        row_opacity_effect = QGraphicsOpacityEffect(row)
        row_opacity_effect.setOpacity(1.0)
        row.setGraphicsEffect(row_opacity_effect)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(6, 6, 6, 6)
        row_lay.setSpacing(8)

        # ─── Drag handle: press-drag to reorder, with a floating semi-
        # transparent "ghost" copy following the cursor — same GhostCard
        # used for reordering asset cards (src/layouts/panels/assets/card.py),
        # reused here instead of native Qt drag-and-drop for a consistent feel.
        handle = QLabel("⠿")
        handle.setFixedWidth(14)
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle.setCursor(Qt.CursorShape.SizeAllCursor)
        handle.setToolTip("Arraste para reordenar")
        handle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px; background: transparent; border: none;")

        drag_state = {"start": None, "ghost": None, "hover_row": None}

        def _find_scroll_host() -> QWidget:
            from PySide6.QtWidgets import QScrollArea
            w = row.parent()
            while w:
                if isinstance(w, QScrollArea):
                    return w.viewport()
                if w.parent() is None:
                    return w
                w = w.parent()
            return row

        def _clear_hover_highlight():
            hover_row = drag_state["hover_row"]
            if hover_row is not None:
                hover_row.setStyleSheet(self._row_style())
                drag_state["hover_row"] = None

        def _handle_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                drag_state["start"] = event.pos()

        def _handle_move(event):
            start = drag_state["start"]
            if start is None:
                return
            if drag_state["ghost"] is None:
                if (event.pos() - start).manhattanLength() <= 6:
                    return
                from src.layouts.panels.assets.card import GhostCard
                host = _find_scroll_host()
                drag_state["ghost"] = GhostCard(row, host)
                row_opacity_effect.setOpacity(0.35)

            ghost = drag_state["ghost"]
            global_pos = event.globalPosition().toPoint()
            # card_offset is relative to the row, not the handle — approximate
            # with the handle's own offset within the row so the ghost tracks
            # naturally under the cursor instead of jumping to the row corner.
            offset_in_row = handle.mapTo(row, start)
            ghost.move_to(global_pos, offset_in_row)

            target = self._row_at_global_pos(global_pos)
            if target is not drag_state["hover_row"]:
                _clear_hover_highlight()
                if target is not None and target is not row:
                    target.setStyleSheet(self._row_style(drop_target=True))
                    drag_state["hover_row"] = target

        def _handle_release(event):
            ghost = drag_state["ghost"]
            if ghost is not None:
                ghost.hide()
                ghost.deleteLater()
                target = self._row_at_global_pos(event.globalPosition().toPoint())
                _clear_hover_highlight()
                row_opacity_effect.setOpacity(1.0)
                if target is not None and target is not row:
                    self._on_reorder_layer(row._layer_index, target._layer_index)
            drag_state["start"] = None
            drag_state["ghost"] = None

        handle.mousePressEvent = _handle_press
        handle.mouseMoveEvent = _handle_move
        handle.mouseReleaseEvent = _handle_release
        row_lay.addWidget(handle)

        # ─── Thumbnail + transparency badge (mirrors the compact style used
        # for static background images in terrain/background.py) ───
        thumb_col = QVBoxLayout()
        thumb_col.setSpacing(1)

        thumb = QLabel()
        thumb.setFixedSize(36, 36)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background: rgba(0,0,0,0.2); border-radius: 3px;")
        pix = QPixmap(layer.image_path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                QSize(36, 36), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        thumb_col.addWidget(thumb)

        transparent = _has_transparency(layer.image_path)
        alpha_lbl = QLabel("alfa ✓" if transparent else "sem alfa")
        alpha_lbl.setFixedWidth(36)
        alpha_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        alpha_color = Colors.SUCCESS if transparent else Colors.WARNING
        alpha_lbl.setStyleSheet(f"color: {alpha_color}; font-size: 7pt; background: transparent; border: none;")
        alpha_lbl.setToolTip(
            "Esta imagem tem canal de transparência" if transparent
            else "Esta imagem não tem transparência — pode cobrir totalmente as camadas atrás dela"
        )
        thumb_col.addWidget(alpha_lbl)
        row_lay.addLayout(thumb_col)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        # Compact name — single small label, double-click to rename in place
        # (same double-click-to-edit convention as NumberStepper), instead of
        # a full-width name row with a dedicated rename button.
        display_name = layer.name or os.path.basename(layer.image_path)
        name_stack = QStackedWidget()
        name_stack.setStyleSheet("background: transparent; border: none;")
        name_stack.setFixedHeight(16)
        name_label = QLabel()
        name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 8pt; background: transparent; border: none;")
        name_label.setToolTip(display_name)

        def _set_elided_name(text: str):
            metrics = name_label.fontMetrics()
            name_label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, 140))
            name_label.setToolTip(text)

        _set_elided_name(display_name)
        name_label.mouseDoubleClickEvent = lambda e: _start_rename()

        name_edit = QLineEdit(display_name)
        name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 8pt;
                background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                border-radius: 3px; padding: 0 4px;
            }}
        """)
        name_stack.addWidget(name_label)
        name_stack.addWidget(name_edit)

        def _start_rename():
            name_edit.setText(name_label.toolTip())
            name_stack.setCurrentIndex(1)
            name_edit.setFocus()
            name_edit.selectAll()

        def _finish_rename():
            if name_stack.currentIndex() != 1:
                return
            new_name = name_edit.text().strip()
            if new_name and new_name != name_label.toolTip():
                _set_elided_name(new_name)
                self._on_param_changed(index, "name", new_name)
            name_stack.setCurrentIndex(0)

        name_edit.returnPressed.connect(_finish_rename)
        name_edit.editingFinished.connect(_finish_rename)
        info_col.addWidget(name_stack)

        # ─── Motion mode + tile mode (tile mode only matters while scrolling) ───
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)

        motion_lbl = QLabel("Movimento:")
        motion_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        mode_row.addWidget(motion_lbl)

        motion_combo = QComboBox()
        motion_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        motion_combo.setStyleSheet(self._combo_style())
        for key, label in _MOTION_MODES:
            motion_combo.addItem(label, key)
        motion_combo.setCurrentIndex([k for k, _ in _MOTION_MODES].index(layer.motion_mode))
        motion_combo.currentIndexChanged.connect(
            lambda i, idx=index, combo=motion_combo: self._on_motion_mode_changed(idx, combo.itemData(i))
        )
        mode_row.addWidget(motion_combo)

        if layer.motion_mode == "scroll":
            tile_lbl = QLabel("Costura:")
            tile_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
            mode_row.addWidget(tile_lbl)

            tile_combo = QComboBox()
            tile_combo.setCursor(Qt.CursorShape.PointingHandCursor)
            tile_combo.setStyleSheet(self._combo_style())
            for key, label in _TILE_MODES:
                tile_combo.addItem(label, key)
            tile_combo.setCurrentIndex([k for k, _ in _TILE_MODES].index(layer.tile_mode))
            tile_combo.currentIndexChanged.connect(
                lambda i, idx=index, combo=tile_combo: self._on_tile_mode_changed(idx, combo.itemData(i))
            )
            mode_row.addWidget(tile_combo)

        mode_row.addStretch()
        info_col.addLayout(mode_row)

        params_row = QHBoxLayout()
        params_row.setSpacing(6)

        if layer.motion_mode == "orbit":
            radius_stepper = NumberStepper("Raio", "🎯", 0, 300, layer.orbit_radius, step=1, decimals=0, suffix="px")
            radius_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "orbit_radius", v))
            params_row.addWidget(radius_stepper)

            orbit_period_stepper = NumberStepper("Período", "⏱", 0.5, 60, layer.orbit_period, step=0.5, decimals=1, suffix="s")
            orbit_period_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "orbit_period", v))
            params_row.addWidget(orbit_period_stepper)
        else:
            # Vel. X/Vel. Y (speed_x/speed_y) used to live here, but parallax
            # layers no longer track the camera pan at all (see Viewport.
            # _draw_parallax_layer) — they're pure background decoration, not
            # something that should shift when you drag/pan the canvas.
            # "Scroll" now just means "static tiled background"; the old
            # speed fields stay on ParallaxLayer (so existing presets still
            # load) but nothing reads them anymore, so there's no control
            # for them here either.
            fixed_lbl = QLabel("Fixo na tela — não se move com o pan do mapa")
            fixed_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; font-style: italic; background: transparent; border: none;")
            params_row.addWidget(fixed_lbl)

        opacity_stepper = NumberStepper("Opac.", "👁", 0, 100, layer.opacity * 100, step=1, decimals=0, suffix="%")
        opacity_stepper.setToolTip(
            "Opacidade base da camada — continua valendo mesmo com \"Pulsar opacidade\" ligado em Efeitos "
            "(o pulso multiplica em cima deste valor, não o substitui)"
        )
        opacity_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "opacity", v / 100.0))
        params_row.addWidget(opacity_stepper)

        # Not editable — the stacking order is just the position in this
        # list (first added = drawn first = further back), so this label
        # only reflects that; there's no separate value to type in.
        order_lbl = QLabel(f"🧱 #{index + 1}")
        order_lbl.setToolTip("Ordem de empilhamento — a posição da camada nesta lista")
        order_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        params_row.addWidget(order_lbl)

        info_col.addLayout(params_row)

        # ─── Collapsible "Efeitos" (opacity/scale/rotation pulses) ───
        effects_btn = QToolButton()
        effects_btn.setText("▶ 🎬 Efeitos")
        effects_btn.setCheckable(True)
        effects_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        effects_btn.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: 8pt; text-align: left; padding: 2px 0; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )

        effects_widget = QWidget()
        effects_widget.setVisible(False)
        effects_outer = QVBoxLayout(effects_widget)
        effects_outer.setContentsMargins(0, 4, 0, 0)
        effects_outer.setSpacing(0)

        # One shared card for the whole "Efeitos" section instead of 4
        # separately-bordered/padded frames stacked on top of each other —
        # that used to cost 4x the frame margin/border overhead plus a
        # dedicated full-width checkbox row above each pulse's steppers.
        # Checkbox now sits inline with its steppers (same row), matching
        # the shader-effects rows below, which already did this correctly.
        effects_card = QFrame()
        effects_card.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.02); border-radius: 4px; }}")
        effects_lay = QVBoxLayout(effects_card)
        effects_lay.setContentsMargins(6, 6, 6, 6)
        effects_lay.setSpacing(4)

        opacity_pulse_row = self._build_minmax_pulse_row(
            index=index, title="Pulsar opacidade",
            enabled=layer.opacity_pulse,
            min_display=layer.opacity_min * 100, max_display=layer.opacity_max * 100,
            period=layer.opacity_period,
            enabled_key="opacity_pulse", min_key="opacity_min", max_key="opacity_max",
            period_key="opacity_period", write_scale=100.0, suffix="%", val_range=(0, 100),
            tooltip=(
                "Min./Máx. são uma fração da opacidade base (\"Opac.\" acima) — não um valor absoluto. "
                "Ex.: Opac. 80% + faixa 60%-100% oscila entre 48% e 80% de opacidade visível."
            ),
        )
        effects_lay.addLayout(opacity_pulse_row)
        effects_lay.addWidget(_divider())
        effects_lay.addLayout(self._build_minmax_pulse_row(
            index=index, title="Escala",
            enabled=layer.scale_pulse,
            min_display=layer.scale_min, max_display=layer.scale_max,
            period=layer.scale_period,
            enabled_key="scale_pulse", min_key="scale_min", max_key="scale_max",
            period_key="scale_period", write_scale=1.0, suffix="%", val_range=(10, 300),
            tooltip="Faz a camada crescer/encolher periodicamente entre Mín. e Máx. (em % do tamanho original).",
        ))
        effects_lay.addWidget(_divider())
        effects_lay.addLayout(self._build_amplitude_pulse_row(
            index=index, title="Rotação",
            enabled=layer.rotation_pulse, amplitude=layer.rotation_amplitude,
            period=layer.rotation_period,
            enabled_key="rotation_pulse", amplitude_key="rotation_amplitude",
            period_key="rotation_period",
            tooltip="Balança a camada de um lado a outro entre -Amplitude e +Amplitude graus.",
        ))
        effects_lay.addWidget(_divider())
        effects_lay.addLayout(self._build_shader_effects_section(index, layer))

        effects_outer.addWidget(effects_card)

        def _toggle_effects(checked, btn=effects_btn, widget=effects_widget):
            widget.setVisible(checked)
            btn.setText(("▼" if checked else "▶") + " 🎬 Efeitos")

        effects_btn.toggled.connect(_toggle_effects)

        info_col.addWidget(effects_btn)
        info_col.addWidget(effects_widget)

        row_lay.addLayout(info_col, 1)

        del_btn = QToolButton()
        del_btn.setText("🗑")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; font-size: 10px; "
            f"color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}"
        )
        del_btn.clicked.connect(lambda checked=False, i=index: self._on_remove_layer(i))
        row_lay.addWidget(del_btn)

        return row

    def _on_param_changed(self, index: int, key: str, value):
        get_parallax_library().update_layer(self.preset_key, index, **{key: value})

    def _on_motion_mode_changed(self, index: int, mode: str):
        self._on_param_changed(index, "motion_mode", mode)
        # Full rebuild: switching modes swaps which steppers/buttons are
        # shown for this row (Vel. X/Y vs Raio/Período, tile-mode buttons
        # appear only in scroll mode), same pattern as other structural
        # changes in this file.
        self._refresh_layers()

    def _on_tile_mode_changed(self, index: int, mode: str):
        self._on_param_changed(index, "tile_mode", mode)
        self._refresh_layers()

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 3px; padding: 1px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 8pt;
            }}
            QComboBox:hover {{ border-color: {Colors.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY}; selection-background-color: {Colors.ACCENT_DIM};
                border: 1px solid {Colors.BORDER_SUBTLE};
            }}
        """

    def _build_minmax_pulse_row(
        self, index: int, title: str, enabled: bool, min_display: float, max_display: float,
        period: float, enabled_key: str, min_key: str, max_key: str, period_key: str,
        write_scale: float, suffix: str, val_range: tuple, tooltip: str = "",
    ) -> QHBoxLayout:
        """Checkbox inline with its steppers in one row instead of a
        dedicated full-width checkbox row above them — same shape as
        _build_shader_effect_row, just with a fixed (not free-form) set of
        steppers. Saves a whole row per pulse type."""
        row = QHBoxLayout()
        row.setSpacing(6)

        check = QCheckBox(title)
        check.setChecked(enabled)
        check.setStyleSheet(f"QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; spacing: 6px; }}")
        check.toggled.connect(lambda v, i=index, k=enabled_key: self._on_param_changed(i, k, v))
        if tooltip:
            check.setToolTip(tooltip)
        row.addWidget(check)

        lo, hi = val_range

        min_stepper = NumberStepper("Mín.", "▽", lo, hi, min_display, step=1, decimals=0, suffix=suffix)
        min_stepper.value_changed.connect(
            lambda v, i=index, k=min_key, s=write_scale: self._on_param_changed(i, k, v / s)
        )
        row.addWidget(min_stepper)

        max_stepper = NumberStepper("Máx.", "△", lo, hi, max_display, step=1, decimals=0, suffix=suffix)
        max_stepper.value_changed.connect(
            lambda v, i=index, k=max_key, s=write_scale: self._on_param_changed(i, k, v / s)
        )
        row.addWidget(max_stepper)

        period_stepper = NumberStepper("Período", "⏱", 0.5, 60, period, step=0.5, decimals=1, suffix="s")
        period_stepper.value_changed.connect(lambda v, i=index, k=period_key: self._on_param_changed(i, k, v))
        row.addWidget(period_stepper)

        return row

    def _build_amplitude_pulse_row(
        self, index: int, title: str, enabled: bool, amplitude: float, period: float,
        enabled_key: str, amplitude_key: str, period_key: str, tooltip: str = "",
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        check = QCheckBox(title)
        check.setChecked(enabled)
        check.setStyleSheet(f"QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; spacing: 6px; }}")
        check.toggled.connect(lambda v, i=index, k=enabled_key: self._on_param_changed(i, k, v))
        if tooltip:
            check.setToolTip(tooltip)
        row.addWidget(check)

        amp_stepper = NumberStepper("Amplitude", "↻", 0, 45, amplitude, step=0.5, decimals=1, suffix="°")
        amp_stepper.value_changed.connect(lambda v, i=index, k=amplitude_key: self._on_param_changed(i, k, v))
        row.addWidget(amp_stepper)

        period_stepper = NumberStepper("Período", "⏱", 0.5, 60, period, step=0.5, decimals=1, suffix="s")
        period_stepper.value_changed.connect(lambda v, i=index, k=period_key: self._on_param_changed(i, k, v))
        row.addWidget(period_stepper)

        return row

    def _build_shader_effects_section(self, index: int, layer) -> QVBoxLayout:
        """Lightweight CPU 'shaders' (tint/blur/chromatic/wave) — a free-form
        list, unlike the fixed opacity/scale/rotation pulses above, since a
        layer can have zero, one, or several of these stacked. No frame of
        its own anymore — it shares the one "Efeitos" card built by the
        caller (_build_layer_row) instead of stacking a 4th bordered box."""
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("Efeitos visuais (shaders)")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; border: none;")
        header.addWidget(title)
        header.addStretch()

        kind_combo = QComboBox()
        kind_combo.setStyleSheet(self._combo_style())
        kind_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for kind, label in EFFECT_KINDS:
            kind_combo.addItem(label, kind)
        # Explains each option before it's even added — the checkbox row
        # created after "+ Efeito" repeats the same tooltip, but a user
        # deciding WHICH effect to add couldn't see this at all before.
        for i, (kind, _label) in enumerate(EFFECT_KINDS):
            kind_combo.setItemData(i, _EFFECT_TOOLTIPS.get(kind, ""), Qt.ItemDataRole.ToolTipRole)
        header.addWidget(kind_combo)

        add_btn = QToolButton()
        add_btn.setText("+ Efeito")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; padding: 2px 6px; "
            f"color: {Colors.ACCENT}; font-size: 8pt; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_btn.clicked.connect(lambda checked=False, i=index, combo=kind_combo: self._on_add_effect(i, combo.currentData()))
        header.addWidget(add_btn)
        lay.addLayout(header)

        for effect_index, effect in enumerate(layer.effects):
            lay.addWidget(self._build_shader_effect_row(index, effect_index, effect))

        return lay

    def _build_shader_effect_row(self, index: int, effect_index: int, effect) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(6)

        check = QCheckBox(_EFFECT_LABELS.get(effect.kind, effect.kind))
        check.setChecked(effect.enabled)
        check.setStyleSheet(f"QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; background: transparent; spacing: 4px; }}")
        check.toggled.connect(lambda v, i=index, ei=effect_index: self._on_effect_param_changed(i, ei, enabled=v))
        tooltip = _EFFECT_TOOLTIPS.get(effect.kind, "")
        if tooltip:
            check.setToolTip(tooltip)
            row.setToolTip(tooltip)
        lay.addWidget(check)

        def _param_stepper(label, icon, lo, hi, value, step, decimals, suffix, key, scale=1.0):
            stepper = NumberStepper(label, icon, lo, hi, value * scale, step=step, decimals=decimals, suffix=suffix)
            stepper.value_changed.connect(
                lambda v, i=index, ei=effect_index, k=key, s=scale: self._on_effect_param_changed(i, ei, params={k: v / s})
            )
            lay.addWidget(stepper)

        if effect.kind == "tint":
            color_edit = QLineEdit(effect.params.get("color", "#4FC3F7"))
            color_edit.setFixedWidth(64)
            color_edit.setStyleSheet(f"""
                QLineEdit {{
                    color: {Colors.TEXT_PRIMARY}; font-size: 8pt;
                    background: rgba(255,255,255,0.08); border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 3px; padding: 0 4px;
                }}
            """)
            color_edit.editingFinished.connect(
                lambda i=index, ei=effect_index, edit=color_edit: self._on_effect_param_changed(i, ei, params={"color": edit.text().strip()})
            )
            lay.addWidget(color_edit)
            _param_stepper("Força", "🎨", 0, 100, effect.params.get("strength", 0.3), 1, 0, "%", "strength", scale=100.0)
        elif effect.kind == "blur":
            _param_stepper("Raio", "💧", 0, 30, effect.params.get("radius", 4.0), 0.5, 1, "px", "radius")
        elif effect.kind == "chromatic":
            _param_stepper("Desloc.", "🌈", 0, 20, effect.params.get("offset_px", 2.0), 0.5, 1, "px", "offset_px")
        elif effect.kind == "wave":
            _param_stepper("Amplit.", "〰", 0, 50, effect.params.get("amplitude", 6.0), 1, 0, "px", "amplitude")
            _param_stepper("Freq.", "≋", 0.01, 1.0, effect.params.get("frequency", 0.05), 0.01, 2, "", "frequency")
            _param_stepper("Veloc.", "⏩", 0, 10, effect.params.get("speed", 1.0), 0.1, 1, "", "speed")

        lay.addStretch()

        del_btn = QToolButton()
        del_btn.setText("✕")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QToolButton {{ border: none; font-size: 9px; color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        del_btn.clicked.connect(lambda checked=False, i=index, ei=effect_index: self._on_remove_effect(i, ei))
        lay.addWidget(del_btn)

        return row

    def _on_add_effect(self, index: int, kind):
        if not kind:
            return
        get_parallax_library().add_effect(self.preset_key, index, kind)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _on_remove_effect(self, index: int, effect_index: int):
        get_parallax_library().remove_effect(self.preset_key, index, effect_index)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _on_effect_param_changed(self, index: int, effect_index: int, enabled=None, params=None):
        kwargs = {}
        if enabled is not None:
            kwargs["enabled"] = enabled
        if params is not None:
            kwargs["params"] = params
        get_parallax_library().update_effect(self.preset_key, index, effect_index, **kwargs)

    def _on_remove_layer(self, index: int):
        get_parallax_library().remove_layer(self.preset_key, index)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _on_reorder_layer(self, source_index: int, target_index: int):
        preset = get_parallax_library().get_preset(self.preset_key)
        if preset and _reorder_hides_layer(preset.layers, source_index, target_index):
            # Rejected — see _reorder_hides_layer. Still rebuild so the
            # dragged row snaps back to its real (unchanged) position
            # instead of appearing stuck wherever the ghost was dropped.
            self._refresh_layers()
            return
        get_parallax_library().reorder_layer(self.preset_key, source_index, target_index)
        # Full rebuild: the "#N" position labels and every row's captured
        # `index` closure need to reflect the new order.
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def card_count(self) -> int:
        preset = get_parallax_library().get_preset(self.preset_key)
        return len(preset.layers) if preset else 0
