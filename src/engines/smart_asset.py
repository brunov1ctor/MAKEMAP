"""FASE 19 — Smart Asset Engine."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QPointF


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class SmartChild:
    asset_id: str
    offset: QPointF = field(default_factory=lambda: QPointF(0, 0))
    offset_random: float = 0.0   # randomize offset within this radius
    scale: float = 1.0
    scale_random: float = 0.0    # ± variation
    rotation: float = 0.0
    rotation_random: float = 0.0
    probability: float = 1.0     # 0-1, chance to spawn
    count: int = 1
    count_random: int = 0        # ± variation
    is_smart: bool = False       # if True, child also triggers its own rules


@dataclass
class SmartRule:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_asset_id: str = ""
    children: list[SmartChild] = field(default_factory=list)
    enabled: bool = True
    max_depth: int = 3


@dataclass
class GeneratedChild:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = ""
    position: QPointF = field(default_factory=lambda: QPointF(0, 0))
    rotation: float = 0.0
    scale: float = 1.0
    parent_id: Optional[str] = None
    depth: int = 0


@dataclass
class SmartPlacement:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_asset_id: str = ""
    position: QPointF = field(default_factory=lambda: QPointF(0, 0))
    items: list[GeneratedChild] = field(default_factory=list)


# ─── Smart Asset Engine ──────────────────────────────────────────────────────

class SmartAssetEngine:
    def __init__(self):
        self._rules: dict[str, SmartRule] = {}
        self._placements: dict[str, SmartPlacement] = {}
        self._seed: int = 0

    # ─── Rule Management ─────────────────────────────────────────────────

    def add_rule(self, rule: SmartRule):
        self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> Optional[SmartRule]:
        return self._rules.pop(rule_id, None)

    def get_rules_for(self, asset_id: str) -> list[SmartRule]:
        return [r for r in self._rules.values()
                if r.trigger_asset_id == asset_id and r.enabled]

    def get_all_rules(self) -> list[SmartRule]:
        return list(self._rules.values())

    def set_rule_enabled(self, rule_id: str, enabled: bool):
        rule = self._rules.get(rule_id)
        if rule:
            rule.enabled = enabled

    # ─── Placement ───────────────────────────────────────────────────────

    def place(self, asset_id: str, position: QPointF,
              seed: int = None) -> SmartPlacement:
        """Place a smart asset and generate its chain."""
        rng = random.Random(seed if seed is not None else self._seed)
        self._seed += 1
        placement = SmartPlacement(
            trigger_asset_id=asset_id, position=position)
        rules = self.get_rules_for(asset_id)
        for rule in rules:
            self._generate_children(
                rule, position, None, 0, rule.max_depth, rng, placement.items)
        self._placements[placement.id] = placement
        return placement

    def _generate_children(self, rule: SmartRule, parent_pos: QPointF,
                           parent_id: Optional[str], depth: int,
                           max_depth: int, rng: random.Random,
                           out: list[GeneratedChild]):
        if depth >= max_depth:
            return
        for child_def in rule.children:
            if rng.random() > child_def.probability:
                continue
            count = child_def.count + rng.randint(-child_def.count_random, child_def.count_random)
            count = max(0, count)
            for _ in range(count):
                # Position
                ox = child_def.offset.x() + rng.uniform(-child_def.offset_random, child_def.offset_random)
                oy = child_def.offset.y() + rng.uniform(-child_def.offset_random, child_def.offset_random)
                pos = QPointF(parent_pos.x() + ox, parent_pos.y() + oy)
                # Transform
                rot = child_def.rotation + rng.uniform(-child_def.rotation_random, child_def.rotation_random)
                scale = child_def.scale + rng.uniform(-child_def.scale_random, child_def.scale_random)
                scale = max(0.1, scale)

                item = GeneratedChild(
                    asset_id=child_def.asset_id, position=pos,
                    rotation=rot, scale=scale,
                    parent_id=parent_id, depth=depth + 1,
                )
                out.append(item)

                # Recursive if child is smart
                if child_def.is_smart:
                    child_rules = self.get_rules_for(child_def.asset_id)
                    for cr in child_rules:
                        self._generate_children(
                            cr, pos, item.id, depth + 1, max_depth, rng, out)

    # ─── Placement Management ────────────────────────────────────────────

    def remove_placement(self, placement_id: str) -> Optional[SmartPlacement]:
        return self._placements.pop(placement_id, None)

    def get_placement(self, placement_id: str) -> Optional[SmartPlacement]:
        return self._placements.get(placement_id)

    def get_all_placements(self) -> list[SmartPlacement]:
        return list(self._placements.values())

    # ─── Presets ─────────────────────────────────────────────────────────

    def preset_castle(self) -> SmartRule:
        rule = SmartRule(trigger_asset_id="castle", children=[
            SmartChild(asset_id="wall", offset=QPointF(60, 0), count=4,
                       offset_random=20, rotation_random=90, is_smart=True),
            SmartChild(asset_id="gate", offset=QPointF(0, 70), probability=0.8),
            SmartChild(asset_id="road", offset=QPointF(0, 120), is_smart=True),
            SmartChild(asset_id="tree", offset=QPointF(80, 80), count=3,
                       offset_random=40, scale_random=0.3),
        ])
        self.add_rule(rule)
        return rule

    def preset_mountain(self) -> SmartRule:
        rule = SmartRule(trigger_asset_id="mountain", children=[
            SmartChild(asset_id="rock", offset=QPointF(30, 40), count=3,
                       offset_random=25, scale=0.6, scale_random=0.2),
            SmartChild(asset_id="grass", offset=QPointF(-20, 50), count=2,
                       offset_random=15, probability=0.7),
            SmartChild(asset_id="shadow", offset=QPointF(15, 10), scale=1.2),
        ])
        self.add_rule(rule)
        return rule

    def preset_village(self) -> SmartRule:
        rule = SmartRule(trigger_asset_id="village", children=[
            SmartChild(asset_id="house", offset=QPointF(0, 0), count=5,
                       offset_random=60, rotation_random=15, scale_random=0.2),
            SmartChild(asset_id="road", offset=QPointF(0, 30), count=2,
                       offset_random=40, is_smart=True),
            SmartChild(asset_id="tree", offset=QPointF(50, 50), count=4,
                       offset_random=50, scale_random=0.3, probability=0.8),
        ])
        self.add_rule(rule)
        return rule

    def preset_lake(self) -> SmartRule:
        rule = SmartRule(trigger_asset_id="lake", children=[
            SmartChild(asset_id="margin", offset=QPointF(0, 0), count=6,
                       offset_random=30, rotation_random=60),
            SmartChild(asset_id="reflection", offset=QPointF(0, 5), scale=1.0,
                       probability=0.9),
            SmartChild(asset_id="vegetation", offset=QPointF(40, 0), count=3,
                       offset_random=35, scale_random=0.2),
        ])
        self.add_rule(rule)
        return rule

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def placement_count(self) -> int:
        return len(self._placements)
