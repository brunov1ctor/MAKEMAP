"""Standalone widget classes used inside MobEditPanel's sections — each is
"dumb"/signal-only (no calls back into MobEditPanel; every interaction goes
through a Qt signal MobEditPanel connects after construction), so they live
here instead of inline in mob_edit_panel.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QWidget, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.mobs.edit_helpers import _rarity_chip_label


class _DropImageButton(QToolButton):
    """The Visão Geral portrait button — click to browse (existing
    behavior, wired by OverviewSectionMixin) plus drag-and-drop of an image
    file straight from Explorer/Finder, same idea as the Importar _DropZone
    (panel_widgets.py) but sized/shaped as the portrait thumbnail itself
    rather than a standalone big drop target."""

    image_dropped = Signal(str)  # local file path

    _ACCEPTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _first_accepted_path(self, mime_data) -> str | None:
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED_SUFFIXES):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and self._first_accepted_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        path = self._first_accepted_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.image_dropped.emit(path)
        else:
            event.ignore()


class _CollapsibleSection(QFrame):
    """One of the edit panel's 3 top-level sections (Visão Geral /
    Atributos / Informações Extras) — a header button toggles its content
    visible/hidden, so a designer working only with, say, atributos can
    collapse the other two and reclaim vertical space instead of scrolling
    past them every time."""

    def __init__(self, title: str, content: QWidget, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        self._title = title
        self._header_btn = QToolButton()
        self._header_btn.setCheckable(True)
        self._header_btn.setChecked(expanded)
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_PRIMARY};
                font-size: 10px; font-weight: bold; text-align: left; padding: 2px; }}
        """)
        self._header_btn.toggled.connect(self._on_toggled)
        outer.addWidget(self._header_btn)

        # Reparent BEFORE toggling visibility — `content` is a freshly
        # built QWidget() with no parent yet at this point, and calling
        # setVisible(True) on a still-parentless widget makes Qt treat it
        # as a real top-level window and briefly show it as one (a native
        # OS window flash) before the very next line reparents it into
        # this layout. addWidget() first means it already has a parent by
        # the time visibility is touched, so it's never shown as its own
        # window.
        outer.addWidget(content)
        content.setVisible(expanded)
        self._content = content
        self._refresh_header_text()

    def _on_toggled(self, checked: bool):
        self._content.setVisible(checked)
        self._refresh_header_text()

    def _refresh_header_text(self):
        arrow = "▾" if self._header_btn.isChecked() else "▸"
        self._header_btn.setText(f"{arrow} {self._title}")


class _DropTile(QFrame):
    """One square tile in Drops Principais — item icon + drop rate below
    it, matching the reference mock (no name text in the tile itself;
    the item name/qty show as a tooltip instead). Backed by a real Item
    row (self._uow.items) rather than a typed-in name, so the icon and
    future rarity/stat data all come from the same catalog every other
    "loot" reference in the app would use."""

    remove_requested = Signal(str)  # item_id

    SIZE = 92

    def __init__(self, item: dict, rate: float, qty: int, parent=None):
        super().__init__(parent)
        self._item_id = item.get("id", "")
        self.setFixedSize(self.SIZE, self.SIZE + 24)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.addStretch()
        remove_btn = QToolButton()
        remove_btn.setText("✕")
        remove_btn.setFixedSize(15, 15)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: rgba(0,0,0,0.45); color: {Colors.TEXT_SECONDARY}; font-size: 9px; border-radius: 7px; }}
            QToolButton:hover {{ background: {Colors.ERROR}; color: white; }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._item_id))
        top_row.addWidget(remove_btn)
        lay.addLayout(top_row)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setFixedHeight(self.SIZE - 40)
        image_path = item.get("image_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(
                self.SIZE - 16, self.SIZE - 40,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            thumb.setText(item.get("icon") or "🎁")
            thumb.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        lay.addWidget(thumb)

        pct = QLabel(f"{rate:.0f}%" if float(rate).is_integer() else f"{rate:.1f}%")
        pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pct.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(pct)

        name = item.get("name") or "Item removido do catálogo"
        self.setToolTip(f"{name} — {qty}x")


class _AbilityCard(QFrame):
    """One Habilidades entry — matches the reference: a generic art tile
    (tinted by rarity, since no per-ability image field was asked for),
    Nome/Descrição, a raridade chip, and a "..." menu (Editar/Excluir)."""

    edit_requested = Signal(int)
    remove_requested = Signal(int)

    def __init__(self, index: int, ability: dict, parent=None):
        super().__init__(parent)
        self._index = index
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        color = item_rarity_color(ability.get("rarity", "common"))
        thumb = QLabel("✨")
        thumb.setFixedSize(64, 64)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(
            f"font-size: 24px; border-radius: 6px; border: 1px solid {color}88; "
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}33, stop:1 rgba(0,0,0,0.25));"
        )
        row.addWidget(thumb)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        name_caption = QLabel("Nome")
        name_caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        mid.addWidget(name_caption)
        name_lbl = QLabel(ability.get("name") or "Sem nome")
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        mid.addWidget(name_lbl)
        desc_caption = QLabel("Descrição")
        desc_caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        mid.addWidget(desc_caption)
        desc_lbl = QLabel(ability.get("description") or "—")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        mid.addWidget(desc_lbl)
        row.addLayout(mid, 1)

        side = QVBoxLayout()
        side.setSpacing(4)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(_rarity_chip_label(ability.get("rarity", "common")))
        side.addLayout(top)
        menu_row = QHBoxLayout()
        menu_row.addStretch()
        menu_btn = QToolButton()
        menu_btn.setText("⋯")
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)
        menu = QMenu(menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("✏ Editar", lambda: self.edit_requested.emit(self._index))
        menu.addAction("🗑 Excluir", lambda: self.remove_requested.emit(self._index))
        menu_btn.setMenu(menu)
        menu_row.addWidget(menu_btn)
        side.addLayout(menu_row)
        row.addLayout(side)


class _AssetCard(QFrame):
    """One mob_assets row — a stamp file attached to this mob (see
    migration 8's docstring: the eventual canvas "Mobs" placement tool
    will stamp one of these). Same visual shape as _AbilityCard."""

    delete_requested = Signal(str)  # asset id

    def __init__(self, asset: dict, parent=None):
        super().__init__(parent)
        self._asset_id = asset.get("id", "")
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        color = item_rarity_color(asset.get("rarity", "common"))
        thumb = QLabel()
        thumb.setFixedSize(64, 64)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_path = asset.get("file_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            thumb.setText("🗿")
            thumb.setStyleSheet(
                f"font-size: 24px; border-radius: 6px; border: 1px solid {color}88; "
                f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}33, stop:1 rgba(0,0,0,0.25));"
            )
        row.addWidget(thumb)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        name_lbl = QLabel(asset.get("name") or "Sem nome")
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        mid.addWidget(name_lbl)
        size_bytes = asset.get("file_size") or 0
        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        type_lbl = QLabel(asset.get("asset_type") or "Arquivo")
        type_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        meta_row.addWidget(type_lbl)
        size_lbl = QLabel(f"{size_mb:.1f} MB" if size_mb else "")
        size_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        meta_row.addWidget(size_lbl)
        meta_row.addStretch()
        mid.addLayout(meta_row)
        row.addLayout(mid, 1)

        side = QVBoxLayout()
        side.setSpacing(4)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(_rarity_chip_label(asset.get("rarity", "common")))
        side.addLayout(top)
        menu_row = QHBoxLayout()
        menu_row.addStretch()
        menu_btn = QToolButton()
        menu_btn.setText("⋯")
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)
        menu = QMenu(menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self._asset_id))
        menu_btn.setMenu(menu)
        menu_row.addWidget(menu_btn)
        side.addLayout(menu_row)
        row.addLayout(side)
