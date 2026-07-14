"""FASE 20 — MMORPG Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QPointF


# ─── Enums ───────────────────────────────────────────────────────────────────

class EntityType(Enum):
    NPC = auto()
    MOB = auto()
    BOSS = auto()
    WORLD_BOSS = auto()
    QUEST = auto()
    DUNGEON = auto()
    SPAWN = auto()
    PORTAL = auto()
    RESOURCE = auto()


class Faction(Enum):
    NEUTRAL = auto()
    FRIENDLY = auto()
    HOSTILE = auto()
    CUSTOM = auto()


class QuestType(Enum):
    MAIN = auto()
    SIDE = auto()
    DAILY = auto()
    WEEKLY = auto()
    EVENT = auto()
    CHAIN = auto()


class ResourceType(Enum):
    ORE = auto()
    HERB = auto()
    WOOD = auto()
    FISH = auto()
    LEATHER = auto()
    GEM = auto()
    CUSTOM = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class LootEntry:
    item_id: str = ""
    name: str = ""
    drop_rate: float = 0.1
    quantity_min: int = 1
    quantity_max: int = 1


@dataclass
class SpawnConfig:
    area_radius: float = 50.0
    max_count: int = 5
    respawn_time: float = 60.0  # seconds
    conditions: str = ""        # e.g. "night_only", "quest_active"


@dataclass
class BossPhase:
    name: str = ""
    hp_threshold: float = 1.0  # triggers at this % HP
    mechanics: list[str] = field(default_factory=list)
    loot: list[LootEntry] = field(default_factory=list)


@dataclass
class QuestObjective:
    description: str = ""
    target_entity_id: Optional[str] = None
    quantity: int = 1
    objective_type: str = "kill"  # kill, collect, talk, explore


@dataclass
class GameEntity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: EntityType = EntityType.NPC
    name: str = ""
    level: int = 1
    position: QPointF = field(default_factory=lambda: QPointF(0, 0))
    map_id: Optional[str] = None
    icon: str = ""
    visible: bool = True
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # NPC
    dialogue: str = ""
    function: str = ""  # vendor, trainer, quest_giver
    faction: Faction = Faction.NEUTRAL

    # Mob/Boss
    hp: int = 100
    damage: int = 10
    behavior: str = "patrol"  # patrol, guard, wander, static
    loot: list[LootEntry] = field(default_factory=list)
    spawn_config: Optional[SpawnConfig] = None

    # Boss specific
    phases: list[BossPhase] = field(default_factory=list)

    # Quest
    quest_type: QuestType = QuestType.SIDE
    objectives: list[QuestObjective] = field(default_factory=list)
    rewards: list[LootEntry] = field(default_factory=list)
    chain_id: Optional[str] = None
    chain_order: int = 0
    prerequisite_ids: list[str] = field(default_factory=list)

    # Dungeon
    rooms: int = 1
    min_level: int = 1
    max_players: int = 5
    encounters: list[str] = field(default_factory=list)

    # Portal
    destination_map_id: Optional[str] = None
    destination_pos: Optional[QPointF] = None
    requirements: str = ""

    # Resource
    resource_type: ResourceType = ResourceType.ORE
    respawn_time: float = 300.0
    quantity: int = 1

    # Spawn
    spawned_entity_id: Optional[str] = None


@dataclass
class EntityConnection:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    connection_type: str = ""  # quest_giver, drops, guards, patrols_to, leads_to
    metadata: dict = field(default_factory=dict)


@dataclass
class EntityMarker:
    entity_id: str
    position: QPointF
    icon: str = "●"
    color: str = "#FFFFFF"
    radius: float = 30.0
    label_visible: bool = True


# ─── MMORPG Engine ───────────────────────────────────────────────────────────

class MMORPGEngine:
    def __init__(self):
        self._entities: dict[str, GameEntity] = {}
        self._connections: dict[str, EntityConnection] = {}
        self._markers: dict[str, EntityMarker] = {}

    # ─── Entity CRUD ─────────────────────────────────────────────────────

    def add_entity(self, entity: GameEntity) -> GameEntity:
        self._entities[entity.id] = entity
        self._markers[entity.id] = EntityMarker(
            entity_id=entity.id, position=entity.position,
            icon=self._default_icon(entity.entity_type),
            color=self._default_color(entity.entity_type),
        )
        return entity

    def remove_entity(self, entity_id: str) -> Optional[GameEntity]:
        self._markers.pop(entity_id, None)
        # Remove related connections
        to_remove = [c.id for c in self._connections.values()
                     if c.source_id == entity_id or c.target_id == entity_id]
        for cid in to_remove:
            self._connections.pop(cid, None)
        return self._entities.pop(entity_id, None)

    def get_entity(self, entity_id: str) -> Optional[GameEntity]:
        return self._entities.get(entity_id)

    def get_entities_by_type(self, entity_type: EntityType) -> list[GameEntity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    def get_entities_by_map(self, map_id: str) -> list[GameEntity]:
        return [e for e in self._entities.values() if e.map_id == map_id]

    def get_entities_by_tag(self, tag: str) -> list[GameEntity]:
        return [e for e in self._entities.values() if tag in e.tags]

    def find_entity_at(self, point: QPointF, radius: float = 20.0) -> Optional[GameEntity]:
        for entity in self._entities.values():
            if (entity.position - point).manhattanLength() < radius:
                return entity
        return None

    # ─── Connections ─────────────────────────────────────────────────────

    def connect(self, source_id: str, target_id: str,
                connection_type: str, metadata: dict = None) -> Optional[EntityConnection]:
        if source_id not in self._entities or target_id not in self._entities:
            return None
        conn = EntityConnection(
            source_id=source_id, target_id=target_id,
            connection_type=connection_type, metadata=metadata or {},
        )
        self._connections[conn.id] = conn
        return conn

    def disconnect(self, connection_id: str) -> Optional[EntityConnection]:
        return self._connections.pop(connection_id, None)

    def get_connections_for(self, entity_id: str) -> list[EntityConnection]:
        return [c for c in self._connections.values()
                if c.source_id == entity_id or c.target_id == entity_id]

    def get_connections_by_type(self, conn_type: str) -> list[EntityConnection]:
        return [c for c in self._connections.values() if c.connection_type == conn_type]

    # ─── Markers ─────────────────────────────────────────────────────────

    def get_marker(self, entity_id: str) -> Optional[EntityMarker]:
        return self._markers.get(entity_id)

    def get_markers_by_type(self, entity_type: EntityType) -> list[EntityMarker]:
        return [self._markers[e.id] for e in self._entities.values()
                if e.entity_type == entity_type and e.id in self._markers]

    def set_marker_visibility(self, entity_id: str, visible: bool):
        entity = self._entities.get(entity_id)
        if entity:
            entity.visible = visible

    def move_entity(self, entity_id: str, new_pos: QPointF):
        entity = self._entities.get(entity_id)
        if entity:
            entity.position = new_pos
            marker = self._markers.get(entity_id)
            if marker:
                marker.position = new_pos

    # ─── Quest Chains ────────────────────────────────────────────────────

    def get_quest_chain(self, chain_id: str) -> list[GameEntity]:
        quests = [e for e in self._entities.values()
                  if e.entity_type == EntityType.QUEST and e.chain_id == chain_id]
        return sorted(quests, key=lambda q: q.chain_order)

    def validate_quest_chain(self, chain_id: str) -> list[str]:
        """Return list of issues in quest chain."""
        chain = self.get_quest_chain(chain_id)
        issues = []
        if not chain:
            issues.append(f"Chain '{chain_id}' is empty")
            return issues
        for i, quest in enumerate(chain):
            if i > 0 and chain[i - 1].id not in quest.prerequisite_ids:
                issues.append(f"Quest '{quest.name}' missing prerequisite from previous in chain")
        return issues

    # ─── Filters ─────────────────────────────────────────────────────────

    def filter_by_level(self, min_level: int, max_level: int) -> list[GameEntity]:
        return [e for e in self._entities.values()
                if min_level <= e.level <= max_level]

    def filter_by_faction(self, faction: Faction) -> list[GameEntity]:
        return [e for e in self._entities.values() if e.faction == faction]

    # ─── World Systems ───────────────────────────────────────────────────

    def get_level_distribution(self) -> dict[int, int]:
        dist: dict[int, int] = {}
        for e in self._entities.values():
            dist[e.level] = dist.get(e.level, 0) + 1
        return dict(sorted(dist.items()))

    def get_faction_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for e in self._entities.values():
            key = e.faction.name
            summary[key] = summary.get(key, 0) + 1
        return summary

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _default_icon(entity_type: EntityType) -> str:
        icons = {
            EntityType.NPC: "👤", EntityType.MOB: "💀",
            EntityType.BOSS: "👹", EntityType.WORLD_BOSS: "🐉",
            EntityType.QUEST: "❗", EntityType.DUNGEON: "🏰",
            EntityType.SPAWN: "◎", EntityType.PORTAL: "🌀",
            EntityType.RESOURCE: "💎",
        }
        return icons.get(entity_type, "●")

    @staticmethod
    def _default_color(entity_type: EntityType) -> str:
        colors = {
            EntityType.NPC: "#4FC3F7", EntityType.MOB: "#EF5350",
            EntityType.BOSS: "#FF7043", EntityType.WORLD_BOSS: "#AB47BC",
            EntityType.QUEST: "#FFEE58", EntityType.DUNGEON: "#8D6E63",
            EntityType.SPAWN: "#66BB6A", EntityType.PORTAL: "#7E57C2",
            EntityType.RESOURCE: "#26C6DA",
        }
        return colors.get(entity_type, "#FFFFFF")

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
