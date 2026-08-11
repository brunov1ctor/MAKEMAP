"""QuestMediator — liga o botão 🖊 de um nó de Fluxo vinculado (ref_type/
ref_id) às ferramentas reais do mapa principal, no molde de
ProgressionMediator: se o NPC/Mob referenciado já foi colocado no mapa,
seleciona o item real e troca pra ferramenta "Selecionar" (o usuário já pode
arrastar/deletar ali, com undo normal); se ainda não foi colocado, arma o
SpawnTool de verdade (o mesmo do painel de Spawn) já configurado com aquela
entidade, troca pra "Spawn", e restaura a ferramenta anterior assim que o
primeiro stamp é colocado. Nenhuma persistência própria — tudo isso já é
undo-ável e já sincroniza pro banco sozinho (SpawnMediator._sync_to_db,
disparado por history_changed) exatamente como o painel de Spawn faria.

Instanciado ad-hoc pelo MenuViewMediator junto com QuestsPanel (mesmo ciclo
de vida — recriado a cada abertura da view Quests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from src.layouts.panels.quests.map_lookup import find_ref_item

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout
    from src.layouts.panels.quests.panel import QuestsPanel


class QuestMediator:
    def __init__(self, layout: MainLayout, panel: QuestsPanel):
        self._l = layout
        self._panel = panel
        self._previous_tool = ""
        self._pending_stamp_cb = None

        panel.edit_on_map_requested.connect(self._on_edit_on_map_requested)
        panel.closed.connect(self._cancel_pending_placement)
        self._l.canvas.engine.tool_changed.connect(self._on_tool_changed)

    def _on_edit_on_map_requested(self, ref_type: str, ref_id: str, color):
        scene = self._l.canvas.engine.viewport.scene()
        item = find_ref_item(scene, ref_type, ref_id)
        if item is not None:
            self._select_on_map(item)
        else:
            self._begin_placement(ref_type, ref_id)

    # ─── Já colocado: selecionar pra editar/mover ───

    def _select_on_map(self, item):
        engine = self._l.canvas.engine
        engine.selection.set([item])
        engine.tool_manager.activate("Selecionar")
        engine.viewport.center_on_point(item.sceneBoundingRect().center())

    # ─── Ainda não colocado: armar Spawn pra um clique único ───

    def _begin_placement(self, ref_type: str, ref_id: str):
        self._cancel_pending_placement()
        self._l._spawn_med.on_kind_changed(ref_type)
        self._l._spawn_med.on_mob_selected(ref_id)

        engine = self._l.canvas.engine
        self._previous_tool = engine.tool_manager.active_name
        engine.tool_manager.activate("Spawn")

        def _on_placed(entity_id, scene_pos):
            QTimer.singleShot(0, self._finish_placement)

        self._pending_stamp_cb = _on_placed
        engine._spawn_tool.on_stamp_placed(_on_placed)

    def _finish_placement(self):
        if self._pending_stamp_cb is not None:
            tool = self._l.canvas.engine._spawn_tool
            try:
                tool._stamp_placed_callbacks.remove(self._pending_stamp_cb)
            except ValueError:
                pass
            self._pending_stamp_cb = None
        if self._previous_tool:
            self._l.canvas.engine.tool_manager.activate(self._previous_tool)
            self._previous_tool = ""

    def _cancel_pending_placement(self):
        if self._pending_stamp_cb is not None:
            tool = self._l.canvas.engine._spawn_tool
            try:
                tool._stamp_placed_callbacks.remove(self._pending_stamp_cb)
            except ValueError:
                pass
            self._pending_stamp_cb = None
        self._previous_tool = ""

    def _on_tool_changed(self, name: str):
        """O usuário também pode abandonar uma colocação pendente trocando
        de ferramenta na toolbar diretamente — sem isso, o callback pendente
        ficaria registrado esperando um stamp que nunca vai vir do fluxo
        esperado (mesma lógica de ProgressionMediator._on_tool_changed)."""
        if self._pending_stamp_cb is None:
            return
        if name == "Spawn":
            return
        self._cancel_pending_placement()
