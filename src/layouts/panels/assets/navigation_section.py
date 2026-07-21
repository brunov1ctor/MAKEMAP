"""NavigationPresetSection — collapsible header + per-layer rows for one
navigation (compass) preset, shown in the Config panel's Navegação group.
Mirrors ParallaxPresetSection's layout/interaction patterns (drag-to-reorder
rows, inline rename, alpha badge, motion-combo-driven conditional fields)
but with compass-appropriate concepts instead of parallax-scrolling ones:
each layer has a Função (what compass part it represents) and an Animação
(how it behaves, continuously — no more parallax motion/tile/effects).
"""

from __future__ import annotations

import json
import os
import re

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QWidget,
    QFileDialog, QLineEdit, QStackedWidget, QGraphicsOpacityEffect, QComboBox, QCheckBox,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QTimer
from PySide6.QtGui import QPixmap, QImage

from src.styles.tokens import Colors
from src.layouts.panels.stepper import NumberStepper
from src.engines.map.navigation import (
    get_navigation_library, ROLE_KINDS, ANIMATION_KINDS, TIMED_ANIMATIONS,
    DEFAULT_ROLE, DEFAULT_ANIMATION,
)

_ROLE_KEYS = {k for k, _ in ROLE_KINDS}
_ANIMATION_KEYS = {k for k, _ in ANIMATION_KINDS}

_IMG_FILTER = "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"

# camelCase-ish JSON key -> NavigationLayer field name, same idea as
# parallax_section.py's _JSON_*_FIELDS — accepts both the plain field name
# and this list so pasted snippets don't have to match exactly.
_JSON_STR_FIELDS = {"name": "name", "role": "role", "animation": "animation"}
_JSON_FLOAT_FIELDS = {"period": "period", "opacity": "opacity", "scale": "scale"}

# (json key, explanation) — rendered as "// key: doc" comment lines above
# the pasted layers template, same convention as parallax_section.py.
_JSON_PARAM_DOCS = [
    ("name", "nome da camada (só identificação, não afeta o desenho)"),
    ("role", "o que a camada representa: " + ", ".join(f'"{k}" ({label})' for k, label in ROLE_KINDS)),
    ("animation", "como ela se comporta: " + ", ".join(f'"{k}" ({label})' for k, label in ANIMATION_KINDS)),
    ("period", "segundos por ciclo — só usado por rotate_cw, rotate_ccw, pulse e blink"),
    ("opacity", "opacidade base da camada, de 0 a 1"),
    ("scale", "tamanho como fração do círculo base do Papel — 1.0 preenche, ex.: 0.25 pro núcleo pequeno"),
]


def _parse_layers_json(text: str) -> list[dict]:
    """Permissive parser for the layer-config snippets users paste in —
    typically a bare list of JS-style object literals (unquoted keys, no
    enclosing brackets, trailing commas), not strict JSON. Same as
    parallax_section.py's helper of the same name. Raises ValueError with a
    Portuguese message on anything unparseable."""
    text = re.sub(r'//[^\n]*', '', text)
    text = text.strip()
    if not text:
        raise ValueError("Cole um JSON com pelo menos uma camada.")
    if not text.startswith("["):
        text = f"[{text}]"
    text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ValueError("Esperava uma lista de camadas (array).")
    return data


def _has_transparency(image_path: str) -> bool:
    """Whether the image actually has any translucent/transparent pixel —
    same check used for parallax layers, since a navigation layer with no
    alpha will paint as an opaque square instead of a compass shape."""
    img = QImage(image_path)
    if img.isNull() or not img.hasAlphaChannel():
        return False
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    small = small.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(small.height()):
        for x in range(small.width()):
            if small.pixelColor(x, y).alpha() < 250:
                return True
    return False


class NavigationPresetSection(QFrame):
    """One preset: collapsible header (rename/activate/add-layer/delete) + a
    row per layer (thumbnail, função, animação, período, order, delete)."""

    delete_requested = Signal(str)  # preset_key
    reorder_requested = Signal(str, str)  # from_preset_key, to_preset_key

    def __init__(self, preset_key: str, name: str, parent=None):
        super().__init__(parent)
        self.preset_key = preset_key
        self._expanded = True
        self._drop_target = False
        self._is_navigation_preset_section = True
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
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(4)

        # ─── Drag handle: reorders the whole preset relative to its
        # siblings, same GhostCard/hover-highlight pattern the layer rows
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

        # Which preset Compass actually plays — only one at a time, toggling
        # this one on switches every other section's button off (via the
        # library's single active_key + the changed signal all sections
        # listen to in _refresh_active_button).
        self._activate_btn = QToolButton()
        self._activate_btn.setCheckable(True)
        self._activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activate_btn.clicked.connect(self._on_activate_clicked)
        h_lay.addWidget(self._activate_btn)

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

        # Whether the HUD chip (terreno ativo / área do mapa / lat-lon —
        # CompassHUD, see main_layout.py) shows up alongside this preset
        # when it's active and the compass is expanded.
        current_preset = get_navigation_library().get_preset(preset_key)
        info_check = QCheckBox("ℹ Info")
        info_check.setCursor(Qt.CursorShape.PointingHandCursor)
        info_check.setChecked(current_preset.show_info if current_preset else True)
        info_check.setToolTip(
            "Mostrar o chip de terreno ativo / área do mapa / lat-lon junto com esta bússola"
        )
        info_check.setStyleSheet(
            f"QCheckBox {{ color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; spacing: 4px; }}"
        )
        info_check.toggled.connect(self._on_show_info_toggled)
        h_lay.addWidget(info_check)

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
            "Cole ou edite as camadas em JSON (name, role, animation, period, opacity). "
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

        get_navigation_library().changed.connect(self._refresh_active_button)
        self._refresh_active_button()
        self._refresh_layers()

    def _header_style(self, active: bool, drop_target: bool = False) -> str:
        if drop_target:
            border, bg = Colors.ACCENT, "rgba(79,195,247,0.15)"
        else:
            border = Colors.ACCENT if active else Colors.BORDER_SUBTLE
            bg = "rgba(79,195,247,0.08)" if active else "rgba(255,255,255,0.02)"
        return f"QFrame {{ background: {bg}; border: none; border-bottom: 1px solid {border}; }}"

    def _refresh_active_button(self):
        active = get_navigation_library().active_key() == self.preset_key
        self._activate_btn.setChecked(active)
        self._activate_btn.setText("★ Em uso" if active else "☆ Usar no mapa")
        self._activate_btn.setToolTip(
            "Esta é a bússola que está tocando" if active else "Tocar esta bússola no mapa"
        )
        self._activate_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;
                color: {Colors.ACCENT if active else Colors.TEXT_MUTED};
                background: {Colors.ACCENT_DIM if active else 'transparent'};
            }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); color: {Colors.ACCENT}; }}
        """)
        self._header.setStyleSheet(self._header_style(active, self._drop_target))

    def _set_drop_target(self, on: bool):
        self._drop_target = on
        active = get_navigation_library().active_key() == self.preset_key
        self._header.setStyleSheet(self._header_style(active, on))

    @staticmethod
    def _preset_section_at_global_pos(global_pos):
        from PySide6.QtWidgets import QApplication
        w = QApplication.widgetAt(global_pos)
        while w is not None:
            if getattr(w, "_is_navigation_preset_section", False):
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

    def _on_activate_clicked(self):
        lib = get_navigation_library()
        if lib.active_key() == self.preset_key:
            lib.set_active(None)
        else:
            lib.set_active(self.preset_key)

    def _on_show_info_toggled(self, checked: bool):
        get_navigation_library().set_show_info(self.preset_key, checked)

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
            get_navigation_library().rename_preset(self.preset_key, new_name)
        self._name_stack.setCurrentIndex(0)

    def _on_add_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem da camada", "", _IMG_FILTER)
        if not path:
            return
        get_navigation_library().add_layer(self.preset_key, path)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _refresh_json_template_if_open(self):
        """Keep the JSON textbox in sync with the layer list — otherwise
        adding/removing/reordering a layer while the panel is open leaves
        it editing a stale set of rows that no longer matches the screen."""
        if not self._json_widget.isHidden():
            self._json_edit.setPlainText(self._build_json_template())
            self._json_error_lbl.hide()

    def _build_json_template(self) -> str:
        preset = get_navigation_library().get_preset(self.preset_key)
        layers = preset.layers if preset else []
        if not layers:
            # Nothing to attach params to yet — a single default row the
            # user can duplicate once they've added images.
            layers = [None]

        def _row_text(i: int, l) -> str:
            name = (l.name if l else None) or f"camada_{i+1}"
            role = l.role if l else DEFAULT_ROLE
            animation = l.animation if l else DEFAULT_ANIMATION
            period = l.period if l else 6.0
            opacity = l.opacity if l else 1.0
            scale = l.scale if l else 1.0
            return (
                f'  {{\n'
                f'    name: "{name}", role: "{role}", animation: "{animation}",\n'
                f'    period: {period}, opacity: {opacity}, scale: {scale}\n'
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

        preset = get_navigation_library().get_preset(self.preset_key)
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
                elif json_key in _JSON_STR_FIELDS:
                    kwargs[_JSON_STR_FIELDS[json_key]] = str(value)
            if "role" in kwargs and kwargs["role"] not in _ROLE_KEYS:
                kwargs.pop("role")
            if "animation" in kwargs and kwargs["animation"] not in _ANIMATION_KEYS:
                kwargs.pop("animation")
            if kwargs:
                get_navigation_library().update_layer(self.preset_key, index, **kwargs)
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

        preset = get_navigation_library().get_preset(self.preset_key)
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
        from PySide6.QtWidgets import QApplication
        w = QApplication.widgetAt(global_pos)
        while w is not None:
            if getattr(w, "_is_navigation_layer_row", False):
                return w
            w = w.parentWidget()
        return None

    def _build_layer_row(self, index: int, layer) -> QWidget:
        row = QFrame()
        row.setStyleSheet(self._row_style())
        row._is_navigation_layer_row = True
        row._layer_index = index
        row_opacity_effect = QGraphicsOpacityEffect(row)
        row_opacity_effect.setOpacity(1.0)
        row.setGraphicsEffect(row_opacity_effect)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(6, 6, 6, 6)
        row_lay.setSpacing(8)

        # ─── Drag handle: press-drag to reorder, same GhostCard pattern used
        # by ParallaxPresetSection's layer rows.
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

        # ─── Thumbnail + transparency badge ───
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
            else "Esta imagem não tem transparência — vai aparecer como um quadrado opaco na bússola"
        )
        thumb_col.addWidget(alpha_lbl)
        row_lay.addLayout(thumb_col)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

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

        # ─── Função (what compass part) + Animação (how it behaves) ───
        combos_row = QHBoxLayout()
        combos_row.setSpacing(8)

        role_col = QVBoxLayout()
        role_col.setSpacing(2)
        role_lbl = QLabel("Função")
        role_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        role_col.addWidget(role_lbl)
        role_combo = QComboBox()
        role_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        role_combo.setStyleSheet(self._combo_style())
        # Fixed, not just a minimum: options like "Ponteiros secundários"
        # are long, and with only 0-stretch siblings in this row, Qt's box
        # layout was splitting leftover space unevenly (one combo/stepper
        # ballooning past 500px while another stayed cramped) — pinning an
        # exact width sidesteps that ambiguity entirely.
        role_combo.setFixedWidth(170)
        for key, label in ROLE_KINDS:
            role_combo.addItem(label, key)
        role_combo.setCurrentIndex([k for k, _ in ROLE_KINDS].index(layer.role))
        role_combo.currentIndexChanged.connect(
            lambda i, idx=index, combo=role_combo: self._on_param_changed(idx, "role", combo.itemData(i))
        )
        role_col.addWidget(role_combo)
        combos_row.addLayout(role_col)

        anim_col = QVBoxLayout()
        anim_col.setSpacing(2)
        anim_lbl = QLabel("Animação")
        anim_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        anim_col.addWidget(anim_lbl)
        anim_combo = QComboBox()
        anim_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        anim_combo.setStyleSheet(self._combo_style())
        anim_combo.setToolTip(
            "Travado na direção do mapa: gira junto com o anel da bússola, como uma agulha de verdade.\n"
            "Interação: fica normal até o mouse chegar em cima da bússola, aí ganha um brilho de destaque."
        )
        # "Travado na direção do mapa" is the longest option — same
        # reasoning as role_combo's fixed width above.
        anim_combo.setFixedWidth(210)
        for key, label in ANIMATION_KINDS:
            anim_combo.addItem(label, key)
        anim_combo.setCurrentIndex([k for k, _ in ANIMATION_KINDS].index(layer.animation))
        anim_combo.currentIndexChanged.connect(
            lambda i, idx=index, combo=anim_combo: self._on_animation_changed(idx, combo.itemData(i))
        )
        anim_col.addWidget(anim_combo)
        combos_row.addLayout(anim_col)

        opacity_stepper = NumberStepper(
            "Opac.", "👁", 0, 100, layer.opacity * 100, step=1, decimals=0, suffix="%"
        )
        opacity_stepper.setFixedWidth(100)
        opacity_stepper.setToolTip(
            "Opacidade base da camada — continua valendo mesmo com Pulso/Piscar "
            "(a animação multiplica em cima deste valor, não o substitui)"
        )
        opacity_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "opacity", v / 100.0))
        combos_row.addWidget(opacity_stepper)

        scale_stepper = NumberStepper(
            "Tamanho", "⤢", 5, 300, layer.scale * 100, step=1, decimals=0, suffix="%"
        )
        scale_stepper.setFixedWidth(100)
        scale_stepper.setToolTip(
            "Tamanho da camada, como fração do círculo base do seu Papel "
            "(o núcleo, ou a faixa do anel para Anel de rotação/Brilho externo) — "
            "100% preenche esse círculo; menos que isso encolhe a camada dentro dele"
        )
        scale_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "scale", v / 100.0))
        combos_row.addWidget(scale_stepper)
        combos_row.addStretch(1)

        info_col.addLayout(combos_row)

        params_row = QHBoxLayout()
        params_row.setSpacing(6)

        if layer.animation in TIMED_ANIMATIONS:
            period_stepper = NumberStepper(
                "Período", "⏱", 0.5, 60, layer.period, step=0.5, decimals=1, suffix="s"
            )
            period_stepper.setFixedWidth(120)
            period_stepper.setToolTip("Segundos por ciclo completo (uma volta, um pulso, ou um pisca)")
            period_stepper.value_changed.connect(lambda v, i=index: self._on_param_changed(i, "period", v))
            params_row.addWidget(period_stepper)

        order_lbl = QLabel(f"🧭 #{index + 1}")
        order_lbl.setToolTip("Ordem de empilhamento — a posição da camada nesta lista")
        order_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        params_row.addWidget(order_lbl)
        params_row.addStretch(1)

        info_col.addLayout(params_row)
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

    def _combo_style(self) -> str:
        # A visible, opaque background (not just a faint 4% overlay) — same
        # color as the popup list below it, so the closed combo reads
        # clearly as a solid control instead of blending into the row.
        return f"""
            QComboBox {{
                background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 2px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 8pt;
            }}
            QComboBox:hover {{ background: rgba(79,195,247,0.3); border-color: {Colors.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY}; selection-background-color: {Colors.ACCENT_DIM};
                border: 1px solid {Colors.BORDER_SUBTLE};
            }}
        """

    def _on_animation_changed(self, index: int, animation):
        if not animation:
            return
        self._on_param_changed(index, "animation", animation)
        # Full rebuild: switching animation shows/hides the Período stepper,
        # same pattern as parallax's motion-mode switch.
        self._refresh_layers()

    def _on_param_changed(self, index: int, key: str, value):
        get_navigation_library().update_layer(self.preset_key, index, **{key: value})

    def _on_remove_layer(self, index: int):
        get_navigation_library().remove_layer(self.preset_key, index)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def _on_reorder_layer(self, source_index: int, target_index: int):
        get_navigation_library().reorder_layer(self.preset_key, source_index, target_index)
        self._refresh_layers()
        self._refresh_json_template_if_open()

    def card_count(self) -> int:
        preset = get_navigation_library().get_preset(self.preset_key)
        return len(preset.layers) if preset else 0
