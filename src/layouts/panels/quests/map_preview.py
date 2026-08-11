"""QuestMapPreview — a segunda QGraphicsView (view read-only) apontando pra
MESMA cena do mapa principal (window.layout_widget.canvas.engine.viewport.
scene()), pra aba Fluxo poder mostrar de verdade onde os NPCs/Mobs vinculados
a cada nó estão no mapa, em vez de só uma legenda estática.

`setInteractive(False)` é o que garante que essa view nunca edita/seleciona
nada no mapa real por engano — ela só lê a cena (Qt permite várias
QGraphicsView por QGraphicsScene nativamente, sem nenhuma sincronização
manual: qualquer coisa desenhada/movida no mapa principal aparece aqui ao
vivo, e vice-versa não existe porque esta view nunca despacha eventos de
mouse pros itens).

Um NPC/Mob só carrega o próprio id de catálogo quando foi de fato colocado
no mapa via ferramenta Spawn (ver SpawnTool.build_stamp_item) — não existe
tabela de busca id->item, então localizar percorre `scene.items()` na hora,
igual ao que SpawnMediator._sync_to_db já faz.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsView, QGraphicsEllipseItem, QFrame
from PySide6.QtCore import Qt, QRectF, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPen

from src.canvas.z_order import ZOrder
from src.layouts.panels.quests.map_lookup import find_ref_item

_PING_MS = 1800
_FRAME_PADDING = 90


class QuestMapPreview(QGraphicsView):
    def __init__(self, scene_provider=None, viewport_provider=None, parent=None):
        super().__init__(parent)
        self._scene_provider = scene_provider or (lambda: None)
        self._viewport_provider = viewport_provider or (lambda: None)
        self._bg_source = None  # main Viewport, for background_snapshot()
        self._attached_scene = None
        self._ping_item: QGraphicsEllipseItem | None = None
        self._panning = False
        self._pan_last_pos = QPoint()
        # fit_all()/frame_all() can be asked to frame content before this
        # widget has ever been laid out (e.g. FlowTab.load() runs the
        # instant a quest is selected, which can be before Qt hands this
        # view a real viewport size) — fitInView() against a 0x0 viewport
        # computes a degenerate transform, and since showEvent() below only
        # re-fits when the attached scene itself changes (not on every
        # re-show), that bad transform used to stick forever, reading as a
        # permanently blank preview. Retry once real geometry shows up.
        self._pending_fit = None
        # Armed by begin_pick() (see FlowTab's 📌 wiring) — the next left
        # click reports its scene position to the callback instead of
        # starting a pan, so a Quest node's decorative pin can be placed by
        # clicking straight in this mini-map instead of jumping to the main
        # canvas.
        self._pick_callback = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(10, 18, 32))
        # Lê a cena sem participar dela — nenhum clique aqui seleciona,
        # move ou edita um item do mapa real. setInteractive(False) também
        # desativa o ScrollHandDrag nativo do Qt (ele só funciona com a
        # view interativa), então o pan é implementado à mão em
        # mousePressEvent/mouseMoveEvent/mouseReleaseEvent abaixo.
        self.setInteractive(False)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # so Escape can cancel a pending pick
        # Sem altura mínima própria — mora dentro de um LiveSplitter
        # colapsável (ver flow_tab.py) e precisa poder ir a zero quando o
        # usuário arrasta o divisor até esconder de vez a seção do mapa.

        self._ping_timer = QTimer(self)
        self._ping_timer.setSingleShot(True)
        self._ping_timer.timeout.connect(self._clear_ping)

    def showEvent(self, event):
        super().showEvent(event)
        # Only auto-fit when the scene we're pointed at actually changed
        # (first attach, or a different project's map) — not on every
        # re-show. FlowTab.load() already framed this quest's own linked
        # points via frame_all()/fit_all() right after loading; switching
        # away to another content tab and back (a plain QStackedWidget
        # show/hide, same scene throughout) used to re-run fit_all() here
        # and blow that framing back out to the whole world every time.
        if self._attach_scene(only_if_changed=True):
            self.fit_all()
        elif self._pending_fit is not None and self._has_real_geometry():
            pending, self._pending_fit = self._pending_fit, None
            pending()

    def _has_real_geometry(self) -> bool:
        return self.viewport().width() > 1 and self.viewport().height() > 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pending_fit is not None and self._has_real_geometry():
            pending, self._pending_fit = self._pending_fit, None
            pending()

    def _attach_scene(self, only_if_changed: bool = False) -> bool:
        scene = self._scene_provider()
        changed = scene is not self._attached_scene
        if changed:
            self.setScene(scene)
            self._attached_scene = scene
            self._bg_source = self._viewport_provider()
        if only_if_changed:
            return changed and scene is not None
        return scene is not None

    def drawBackground(self, painter, rect: QRectF):
        """The main Viewport paints its terrain/parallax background via its
        own drawBackground() override, which only applies to that one
        QGraphicsView — this secondary view on the same scene never gets it
        and would otherwise render pure black behind the scene's items (see
        MiniMapView.drawBackground, same fix)."""
        if self._bg_source is None:
            super().drawBackground(painter, rect)
            return
        snap = self._bg_source.background_snapshot()
        if snap is None:
            super().drawBackground(painter, rect)
            return
        kind, value = snap
        if kind == "color":
            painter.fillRect(rect, value)
        else:
            painter.drawPixmap(rect, value, QRectF(value.rect()))

    def _find_item(self, ref_type: str, ref_id: str):
        return find_ref_item(self.scene(), ref_type, ref_id)

    # ── API pública ──

    def locate(self, ref_type: str, ref_id: str, color: QColor) -> bool:
        """Centraliza a view no item vinculado e pisca um anel colorido em
        volta dele. Devolve False (sem mover nada) se o projeto ainda não
        tem mapa aberto ou o NPC/Mob nunca foi colocado nele."""
        if not self._attach_scene():
            return False
        item = self._find_item(ref_type, ref_id)
        if item is None:
            return False
        center = item.sceneBoundingRect().center()
        self.centerOn(center)
        self._show_ping(center, color)
        return True

    def locate_point(self, scene_pos, color: QColor) -> bool:
        """Same as locate(), but for a bare scene point — used for a Flow
        node's own decorative pin (see FlowNode.pin), which isn't a real
        placed NPC/Mob item find_ref_item() could look up."""
        if not self._attach_scene():
            return False
        self.centerOn(scene_pos)
        self._show_ping(scene_pos, color)
        return True

    def fit_all(self) -> bool:
        """Enquadra TODO o conteúdo do mapa (não só os nós vinculados a esta
        quest) — o ponto de partida esperado ao abrir/trocar de quest, igual
        a um minimapa sempre mostrando o mundo inteiro primeiro. Devolve
        False sem mexer na view se ainda não há projeto/mapa ou o mapa está
        vazio."""
        if not self._attach_scene():
            return False
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return False
        if not self._has_real_geometry():
            self._pending_fit = self.fit_all
            return True
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def frame_all(self, refs: list[tuple[str, str]]) -> int:
        """Enquadra todos os vínculos já colocados no mapa de uma vez.
        Devolve quantos foram encontrados (0 = nenhum, mantém a view onde
        estava)."""
        if not self._attach_scene():
            return 0
        points = []
        for ref_type, ref_id in refs:
            item = self._find_item(ref_type, ref_id)
            if item is not None:
                points.append(item.sceneBoundingRect().center())
        if not points:
            return 0
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        rect = QRectF(
            min(xs) - _FRAME_PADDING, min(ys) - _FRAME_PADDING,
            (max(xs) - min(xs)) + _FRAME_PADDING * 2,
            (max(ys) - min(ys)) + _FRAME_PADDING * 2,
        )
        if not self._has_real_geometry():
            self._pending_fit = lambda: self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            return len(points)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        return len(points)

    # ── ping visual ──

    def _show_ping(self, center, color: QColor):
        self._clear_ping()
        scene = self.scene()
        if scene is None:
            return
        radius = 28
        ring = QGraphicsEllipseItem(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        ring.setPen(QPen(color, 4))
        ring.setBrush(Qt.BrushStyle.NoBrush)
        ring.setZValue(ZOrder.CURSOR_GHOST)
        scene.addItem(ring)
        self._ping_item = ring
        self._ping_timer.start(_PING_MS)

    def _clear_ping(self):
        if self._ping_item is None:
            return
        try:
            scene = self._ping_item.scene()
            if scene is not None:
                scene.removeItem(self._ping_item)
        except RuntimeError:
            # The underlying C++ QGraphicsEllipseItem can already be gone by
            # the time this fires (2.5s timer) — the shared scene itself
            # got cleared/rebuilt (project closed/reopened) or torn down at
            # app shutdown out from under it. Nothing to remove in that
            # case; just drop our stale reference below.
            pass
        self._ping_item = None

    # ── colocar um pino clicando direto no preview ──

    def begin_pick(self, callback) -> bool:
        """Arms pick mode: the next left click reports its scene position
        to `callback(QPointF)` instead of panning. Cancelled by Escape or
        by arming a new pick before the previous one resolves. Returns
        False (nothing armed) if there's no project/map to click on."""
        if not self._attach_scene():
            return False
        self._pick_callback = callback
        self.setCursor(Qt.CursorShape.CrossCursor)
        return True

    def cancel_pick(self):
        if self._pick_callback is None:
            return
        self._pick_callback = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._pick_callback is not None:
            self.cancel_pick()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── zoom livre com a roda do mouse (sem afetar o mapa principal) ──

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        event.accept()

    # ── pan livre arrastando com o botão esquerdo (setInteractive(False)
    # desliga o ScrollHandDrag nativo do QGraphicsView, então isso substitui
    # ele diretamente pelas barras de rolagem) ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pick_callback is not None:
            callback, self._pick_callback = self._pick_callback, None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            callback(self.mapToScene(event.pos()))
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.scene() is not None:
            self._panning = True
            self._pan_last_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_last_pos
            self._pan_last_pos = event.pos()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._clear_ping()
        self.cancel_pick()
        super().hideEvent(event)
