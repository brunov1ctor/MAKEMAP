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
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen

from src.canvas.z_order import ZOrder

_PING_MS = 1800
_FRAME_PADDING = 90


class QuestMapPreview(QGraphicsView):
    def __init__(self, scene_provider=None, parent=None):
        super().__init__(parent)
        self._scene_provider = scene_provider or (lambda: None)
        self._attached_scene = None
        self._ping_item: QGraphicsEllipseItem | None = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(10, 18, 32))
        # Lê a cena sem participar dela — nenhum clique aqui seleciona,
        # move ou edita um item do mapa real; arrastar ainda pan-eia a
        # view (ScrollHandDrag não depende de setInteractive).
        self.setInteractive(False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
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

    def _attach_scene(self, only_if_changed: bool = False) -> bool:
        scene = self._scene_provider()
        changed = scene is not self._attached_scene
        if changed:
            self.setScene(scene)
            self._attached_scene = scene
        if only_if_changed:
            return changed and scene is not None
        return scene is not None

    @staticmethod
    def _matches(item, ref_type: str, ref_id: str) -> bool:
        data = item.data(0)
        if not isinstance(data, dict):
            return False
        return data.get("item_type") == f"{ref_type}_spawn" and data.get("mob_id") == ref_id

    def _find_item(self, ref_type: str, ref_id: str):
        scene = self.scene()
        if scene is None or not ref_id or ref_type not in ("npc", "mob"):
            return None
        for item in scene.items():
            if self._matches(item, ref_type, ref_id):
                return item
        return None

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

    # ── zoom livre com a roda do mouse (sem afetar o mapa principal) ──

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def hideEvent(self, event):
        self._clear_ping()
        super().hideEvent(event)
