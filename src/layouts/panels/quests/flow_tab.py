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
from PySide6.QtCore import Qt, Signal, QTimer

from src.styles.tokens import Colors
from src.components.live_splitter import LiveSplitter
from src.layouts.panels.quests.constants import panel_frame_style, sub_header
from src.layouts.panels.quests.flow_node import NODE_TYPES, NODE_TYPE_ORDER
from src.layouts.panels.quests.flow_canvas import FlowCanvas
from src.layouts.panels.quests.flow_node_dialog import FlowNodeDialog
from src.layouts.panels.quests.map_preview import QuestMapPreview


class FlowTab(QFrame):
    changed = Signal()

    def __init__(self, scene_provider=None, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._npcs: list[dict] = []
        self._mobs: list[dict] = []

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

        self._map = QuestMapPreview(scene_provider=scene_provider)

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

        header_row = QHBoxLayout()
        header_row.addWidget(sub_header("Fluxo da Quest"))
        header_row.addStretch()
        for key in NODE_TYPE_ORDER:
            meta = NODE_TYPES[key]
            chip = QLabel(f"{meta['icon']} {meta['label']}")
            chip.setStyleSheet(
                f"font-size: 9px; font-weight: bold; color: {meta['color']}; "
                f"background: transparent; border: none; margin-left: 8px;"
            )
            header_row.addWidget(chip)
        lay.addLayout(header_row)

        hint = QLabel(
            "Botão direito no canvas para adicionar um nó · arraste da borda direita de um nó até "
            "outro para conectar · duplo-clique num nó para editar (e vincular a um NPC/Mob do mapa) "
            "· duplo-clique numa seta para nomeá-la (ex.: Sim/Não)."
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
        self._canvas.node_edit_requested.connect(self._on_node_edit_requested)
        self._canvas.node_locate_requested.connect(self._on_node_locate_requested)
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
            # Nada vinculado ainda — não há o que enquadrar de perto, então
            # mostra o mundo inteiro (ver ramo abaixo).
            self._map.fit_all()
            return

        by_id = {}
        for n in nodes:
            node = self._canvas.add_node(
                n.get("type", "objetivo"), n.get("title", ""), n.get("subtitle", ""),
                x=n.get("x", 20), y=n.get("y", 20), node_id=n.get("id", ""),
                ref_type=n.get("ref_type", ""), ref_id=n.get("ref_id", ""), notify=False,
            )
            by_id[node.node_id] = node
        for e in data.get("edges") or []:
            a = by_id.get(e.get("from"))
            b = by_id.get(e.get("to"))
            if a and b:
                self._canvas.add_edge(a, b, e.get("label", ""), notify=False)

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
            "x": n.x(), "y": n.y(), "ref_type": n.ref_type(), "ref_id": n.ref_id(),
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
