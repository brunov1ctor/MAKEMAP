"""Shared floating-popup scaffolding, extracted from
src/layouts/panels/progression/node_dialog.py so more than one panel (the
Progressão node editor, the Explorer icon/color editor, ...) can reuse the
same glass-card-over-dimmed-backdrop popup instead of re-implementing the
focus-race handling below.

A plain child QWidget (semi-transparent backdrop + a glass card) — not a
QDialog, and (after trying it) not a separate top-level window either: a
real top-level window fixed the keyboard-focus race described below, but
introduced a worse problem — it's a genuinely different OS window, so
things like Alt-Tab/window-manager focus changes could leave the main app
window looking "hidden" behind it. Staying an embedded child keeps this
reading as an in-app floating panel, same as every other panel here.

That embedding is exactly why grabbing keyboard focus for a field needs
care: a child widget shares its parent's own top-level window, so if this
popup opens right after another popup (e.g. a "⋮" menu) closes on the same
tick, our setFocus() call can race Windows' own in-flight restoration of
focus to whatever that parent window had before — and lose, leaving
keystrokes routed elsewhere (e.g. the map's WASD-pan shortcut) instead of
the field. _run()/_claim_focus() below retries setFocus() a few times, a
few ms apart, stopping the instant hasFocus() actually confirms it — self-
correcting rather than trusting a single guessed delay (an earlier version
tried draining the queue with QApplication.processEvents() instead, which
turned out to have its own trap: it can dispatch an already-queued close
request before the popup's own QEventLoop starts running, and
QEventLoop.quit() silently no-ops when the loop isn't executing yet — a
real deadlock, not just a hypothetical).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QSizePolicy

from src.layouts.panel_manager import paint_glass_panel


class GlassCard(QFrame):
    """A QFrame painted with the project's shared frosted-glass look
    instead of a flat stylesheet color, so the popup matches the rest of
    the app instead of reading as a native OS window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        paint_glass_panel(self, radius=12)


class PopupOverlay(QWidget):
    """Shared backdrop-plus-glass-card scaffolding — a dimmed scrim filling
    the host widget, with a fixed-width card centered over it. A plain
    embedded child widget (see module docstring for why not a QDialog or a
    separate top-level window). Clicking the backdrop (missing the card)
    cancels."""

    def __init__(self, card_width: int, parent=None):
        super().__init__(parent)
        self._loop: QEventLoop | None = None
        # Set by subclasses to whichever field should start focused (e.g.
        # a QLineEdit).
        self._initial_focus: QWidget | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,0.55);")

        self.card = GlassCard(self)
        self.card.setFixedWidth(card_width)
        self.card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch()
        outer.addWidget(self.card)
        outer.addStretch()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.pos()):
            self._cancel()

    def _cancel(self):
        self._close()

    def _close(self):
        if self._loop is not None:
            self._loop.quit()
        self.hide()
        QTimer.singleShot(0, self.deleteLater)

    def _run(self):
        self._loop = QEventLoop()
        host = self.parentWidget()
        if host is not None:
            self.setGeometry(host.rect())
        self.show()
        self.raise_()
        if self._initial_focus is not None:
            self._claim_focus()
        self._loop.exec()

    def _claim_focus(self, attempts_left: int = 6):
        """Verifies the focus request actually stuck instead of trusting a
        guessed delay (or QApplication.processEvents(), which turned out
        to have its own trap: it can dispatch an already-queued close
        request before self._loop even starts running, and QEventLoop.
        quit() silently does nothing when called on a loop that isn't
        executing yet — a real deadlock this hit during testing, not just
        a hypothetical). Windows can still be mid-restoring focus to
        whatever the parent window had before this popup opened, so the
        very first setFocus() can lose that race; retrying a few times a
        few ms apart, and stopping the moment hasFocus() actually confirms
        it worked, self-corrects without a fixed wait either way."""
        if not self.isVisible() or self._initial_focus is None:
            return
        self._initial_focus.setFocus(Qt.FocusReason.PopupFocusReason)
        if self._initial_focus.hasFocus() or attempts_left <= 0:
            return
        QTimer.singleShot(15, lambda: self._claim_focus(attempts_left - 1))


class IconPickerPopup(PopupOverlay):
    """Small popover grid to pick one emoji — reuses the shared IconPicker
    widget/palette so icon choices are consistent across the app instead
    of free-typing an emoji."""

    def __init__(self, icons: list[str], current: str, parent=None):
        super().__init__(card_width=240, parent=parent)
        self.picked_icon: str | None = None

        from src.layouts.panels.marker.icon_picker import IconPicker

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(0)
        picker = IconPicker(icons, button_size=30, max_height=240, fill=False)
        picker.set_checked(current)
        picker.icon_picked.connect(self._on_picked)
        lay.addWidget(picker)

    def _on_picked(self, icon: str):
        self.picked_icon = icon
        self._close()

    def exec(self) -> str | None:
        self._run()
        return self.picked_icon
