"""RecordListColumn — a coluna esquerda usada pelas duas metades da tela
(LISTA DE CONSTRUÇÕES e LISTA DE DUNGEONS).

Byte-identical à versão de Quests exceto qual `status_dot` colore a bolinha
e qual emoji cai como fallback sem thumbnail — as duas coisas que realmente
variam por entidade agora vivem em src/layouts/panels/shared/record_list.py,
e este módulo só define essas duas (ver _RecordCard.STATUS_DOT/DEFAULT_ICON)
subclasseando a implementação compartilhada."""

from __future__ import annotations

from src.layouts.panels.dungeons.constants import status_dot
from src.layouts.panels.shared.record_list import (
    _RecordCard as _BaseRecordCard,
    RecordListColumn as _BaseRecordListColumn,
)


class _RecordCard(_BaseRecordCard):
    STATUS_DOT = staticmethod(status_dot)
    DEFAULT_ICON = "🏰"


class RecordListColumn(_BaseRecordListColumn):
    """Criar um novo registro é feito pelo botão "+ Novo..." no cabeçalho da
    seção (ver panel.py), não por um card dentro da lista."""

    CARD_CLASS = _RecordCard
