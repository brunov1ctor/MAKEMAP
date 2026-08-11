"""FlowTab — aba de conteúdo "Fluxo": o grafo de nós (Início → Objetivo →
Condição → Sim/Não → Evento → Fim) guardado em `flow_json` (migration 37),
com uma prévia do mapa real do projeto no topo — a mesma QGraphicsScene do
mapa principal (ver map_preview.py), pra clicar no 📍 de um nó vinculado a
um NPC/Mob e ir direto pra onde ele foi colocado.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF

from src.styles.tokens import Colors
from src.components.live_splitter import LiveSplitter
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.quests.constants import panel_frame_style, sub_header
from src.layouts.panels.quests.flow_node import NODE_TYPES, NODE_TYPE_ORDER
from src.layouts.panels.quests.flow_canvas import FlowCanvas, meta_label_default
from src.layouts.panels.quests.flow_node_dialog import FlowNodeDialog
from src.layouts.panels.quests.map_preview import QuestMapPreview
from src.layouts.panels.quests.quest_map_overlay import QuestMapOverlay


class FlowTab(QFrame):
    changed = Signal()
    edit_on_map_requested = Signal(str, str, object)  # ref_type, ref_id, color

    def __init__(self, scene_provider=None, viewport_provider=None, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._npcs: list[dict] = []
        self._mobs: list[dict] = []
        self._viewport_provider = viewport_provider or (lambda: None)
        self._map_overlay = QuestMapOverlay(scene_provider or (lambda: None))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # ── Mapa (seção) e Fluxo (seção), dentro de um LiveSplitter vertical
        # em vez de só empilhados — igual ao resto do app, arrastar o
        # divisor até o topo/fim esconde uma seção por completo (ver
        # setChildrenCollapsible abaixo) em vez de parar numa altura mínima;
        # QuestMapPreview não tem mais altura mínima própria justamente pra
        # isso funcionar. ──
        self._split = LiveSplitter(Qt.Orientation.Vertical)
        self._split.setChildrenCollapsible(True)
        self._split.setHandleWidth(8)
        self._split.addWidget(self._build_map_section(scene_provider))
        self._split.addWidget(self._build_flow_section())
        self._split.setSizes([220, 480])
        outer.addWidget(self._split, 1)

    def _build_map_section(self, scene_provider) -> QWidget:
        section = QFrame()
        section.setObjectName("subpanel")
        section.setStyleSheet(panel_frame_style())
        lay = QVBoxLayout(section)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        self._map = QuestMapPreview(scene_provider=scene_provider, viewport_provider=self._viewport_provider)

        btn_style = f"""
            QToolButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 3px 8px; font-size: 9px; }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); border-color: {Colors.ACCENT}; }}
        """
        map_header = QHBoxLayout()
        map_header.addWidget(sub_header("Mapa e Localizações"))
        map_header.addStretch()
        self._map_status = QLabel("")
        self._map_status.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        map_header.addWidget(self._map_status)
        fit_btn = QToolButton()
        fit_btn.setText("🗺 Ver tudo")
        fit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fit_btn.setStyleSheet(btn_style)
        fit_btn.clicked.connect(self._map.fit_all)
        map_header.addWidget(fit_btn)
        center_btn = QToolButton()
        center_btn.setText("🎯 Centralizar na Quest")
        center_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        center_btn.setStyleSheet(btn_style)
        center_btn.clicked.connect(self._on_center_all)
        map_header.addWidget(center_btn)
        lay.addLayout(map_header)

        lay.addWidget(self._map, 1)
        return section

    def _build_flow_section(self) -> QWidget:
        section = QFrame()
        section.setObjectName("subpanel")
        section.setStyleSheet(panel_frame_style())
        lay = QVBoxLayout(section)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(8)

        lay.addWidget(sub_header("Fluxo da Quest"))

        # Os 5 botões "+ <tipo>" precisam de ~590px numa única linha — mais
        # do que a largura mínima da coluna de conteúdo (360px, ver
        # panel.py:_build_content_column). Um QHBoxLayout rígido deixava os
        # últimos botões vazarem pra fora do frame quando a coluna ficava
        # estreita (clique neles não fazia nada, pois o pixel clicado já não
        # era o botão real) — FlowLayout quebra linha em vez de vazar.
        btns_holder = QWidget()
        btns_holder.setStyleSheet("background: transparent;")
        btns_flow = FlowLayout(btns_holder, spacing=4)
        for key in NODE_TYPE_ORDER:
            meta = NODE_TYPES[key]
            add_btn = QToolButton()
            add_btn.setText(f"+ {meta['icon']} {meta['label']}")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setToolTip(f"Adicionar nó de {meta['label']}")
            add_btn.setStyleSheet(f"""
                QToolButton {{ border: none; border-radius: 6px; font-size: 9px; font-weight: bold;
                    color: {meta['color']}; background: rgba(255,255,255,0.06); padding: 3px 7px; }}
                QToolButton:hover {{ background: rgba(255,255,255,0.14); }}
            """)
            add_btn.clicked.connect(lambda checked=False, k=key: self._canvas.add_node(k, meta_label_default(k)))
            btns_flow.addWidget(add_btn)
        lay.addWidget(btns_holder)

        hint = QLabel(
            "Clique num dos botões acima para adicionar um nó · arraste da borda direita de um nó até "
            "outro para conectar · duplo-clique num nó para editar (e vincular a um NPC/Mob do mapa) "
            "· duplo-clique numa seta para nomeá-la ou removê-la (ex.: Sim/Não) · 🖊 num nó vinculado "
            "coloca o NPC/Mob no mapa se ainda não estiver lá, ou seleciona pra mover se já estiver."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._canvas = FlowCanvas()
        self._canvas.changed.connect(self.changed.emit)
        self._canvas.changed.connect(self._refresh_map_overlay)
        self._canvas.node_edit_requested.connect(self._on_node_edit_requested)
        self._canvas.node_locate_requested.connect(self._on_node_locate_requested)
        self._canvas.node_edit_on_map_requested.connect(self._on_node_edit_on_map_requested)
        self._canvas.node_pin_pick_requested.connect(self._on_node_pin_pick_requested)
        self._canvas.node_pin_locate_requested.connect(self._on_node_pin_locate_requested)
        scroll.setWidget(self._canvas)
        lay.addWidget(scroll, 1)
        return section

    def _on_node_edit_requested(self, node):
        dialog = FlowNodeDialog(
            node.node_type(), node.title(), node.subtitle(),
            ref_type=node.ref_type(), ref_id=node.ref_id(),
            npcs=self._npcs, mobs=self._mobs, parent=self,
        )
        if dialog.exec():
            node_type, title, subtitle, ref_type, ref_id = dialog.values()
            node.set_data(node_type, title or node.title(), subtitle, ref_type, ref_id)
            self.changed.emit()

    def _on_node_locate_requested(self, node):
        found = self._map.locate(node.ref_type(), node.ref_id(), node.color())
        self._map_status.setText("" if found else "Ainda não colocado no mapa.")
        if not found:
            QTimer.singleShot(2500, lambda: self._map_status.setText(""))

    def _on_node_edit_on_map_requested(self, node):
        if not node.ref_id():
            return
        self.edit_on_map_requested.emit(node.ref_type(), node.ref_id(), node.color())

    # ── pino decorativo (📌), colocado clicando direto no mini-mapa ──

    def _on_node_pin_pick_requested(self, node):
        armed = self._map.begin_pick(lambda scene_pos: self._on_pin_picked(node, scene_pos))
        self._map_status.setText(
            "Clique no mapa acima para colocar o marcador (Esc cancela)." if armed
            else "Abra um projeto com mapa antes de colocar um marcador."
        )
        if not armed:
            QTimer.singleShot(2500, lambda: self._map_status.setText(""))

    def _on_pin_picked(self, node, scene_pos):
        self._map_status.setText("")
        self._canvas.set_node_pin(node, scene_pos.x(), scene_pos.y())

    def _on_node_pin_locate_requested(self, node):
        if not node.pin:
            return
        self._map.locate_point(QPointF(node.pin["x"], node.pin["y"]), node.color())

    def _refresh_map_overlay(self):
        self._map_overlay.rebuild(
            self._canvas.nodes(),
            on_marker_moved=self._on_marker_dragged,
            on_marker_remove=self._on_marker_remove,
        )

    def _on_marker_dragged(self, node, scene_pos):
        self._canvas.set_node_pin(node, scene_pos.x(), scene_pos.y())

    def _on_marker_remove(self, node):
        self._canvas.clear_node_pin(node)

    def _on_center_all(self):
        refs = [(n.ref_type(), n.ref_id()) for n in self._canvas.nodes() if n.ref_id()]
        found = self._map.frame_all(refs)
        self._map_status.setText("" if found else "Nenhum nó vinculado está colocado no mapa ainda.")
        if not found:
            QTimer.singleShot(2500, lambda: self._map_status.setText(""))

    # ── API pública ──

    def set_catalog(self, npcs: list[dict], mobs: list[dict]):
        """NPCs/Mobs disponíveis pro picker "Vincular a" do FlowNodeDialog."""
        self._npcs = npcs
        self._mobs = mobs

    def set_empty(self):
        self._canvas.clear()
        self._refresh_map_overlay()
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._canvas.clear()
        data = self._parse(record.get("flow_json"))
        nodes = data.get("nodes") or []
        if not nodes:
            # Sem fluxo salvo ainda — semeia Início/Fim, mesmo ponto de
            # partida que a referência sempre mostra, em vez de um canvas
            # em branco sem nenhuma pista de como começar. notify=False
            # porque isso é o load(), não uma edição do usuário — sem isso
            # cada seleção de uma quest nova dispararia um save imediato.
            start = self._canvas.add_node("inicio", "Início da Quest", x=20, y=80, notify=False)
            end = self._canvas.add_node("fim", "Fim", x=260, y=80, notify=False)
            self._canvas.add_edge(start, end, notify=False)
            self._refresh_map_overlay()
            # Nada vinculado ainda — não há o que enquadrar de perto, então
            # mostra o mundo inteiro (ver ramo abaixo).
            self._map.fit_all()
            return

        by_id = {}
        for n in nodes:
            node = self._canvas.add_node(
                n.get("type", "objetivo"), n.get("title", ""), n.get("subtitle", ""),
                x=n.get("x", 20), y=n.get("y", 20), node_id=n.get("id", ""),
                ref_type=n.get("ref_type", ""), ref_id=n.get("ref_id", ""), pin=n.get("pin"), notify=False,
            )
            by_id[node.node_id] = node
        for e in data.get("edges") or []:
            a = by_id.get(e.get("from"))
            b = by_id.get(e.get("to"))
            if a and b:
                self._canvas.add_edge(a, b, e.get("label", ""), notify=False)
        self._refresh_map_overlay()

        # Enquadra de perto só os pontos ligados a esta quest — mostrar o
        # mapa inteiro por padrão deixava a maior parte da view vazia
        # (sobra) sempre que o mundo é bem maior que a área onde a quest
        # realmente acontece. Só cai pro mundo inteiro (fit_all) quando
        # nenhum vínculo desta quest foi colocado no mapa ainda, já que aí
        # não há nada específico pra enquadrar.
        refs = [(n.get("ref_type", ""), n.get("ref_id", "")) for n in nodes if n.get("ref_id")]
        if not self._map.frame_all(refs):
            self._map.fit_all()

    def collect(self) -> dict:
        nodes = [{
            "id": n.node_id, "type": n.node_type(), "title": n.title(), "subtitle": n.subtitle(),
            "x": n.x(), "y": n.y(), "ref_type": n.ref_type(), "ref_id": n.ref_id(), "pin": n.pin,
        } for n in self._canvas.nodes()]
        edges = [{"from": e["a"].node_id, "to": e["b"].node_id, "label": e.get("label", "")}
                 for e in self._canvas.edges()]
        return {"flow_json": json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)}

    @staticmethod
    def _parse(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        try:
            data = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
