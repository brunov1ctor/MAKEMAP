"""FASE 18 — Procedural Engine."""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QPointF, QRectF


# ─── Enums ───────────────────────────────────────────────────────────────────

class GeneratorType(Enum):
    FOREST = auto()
    MOUNTAIN = auto()
    VILLAGE = auto()
    ROCK = auto()
    CLOUD = auto()
    FOG = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class GeneratedItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: Optional[str] = None
    position: QPointF = field(default_factory=lambda: QPointF(0, 0))
    rotation: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0
    z_offset: float = 0.0


@dataclass
class GeneratorParams:
    area: QRectF = field(default_factory=lambda: QRectF(0, 0, 500, 500))
    density: float = 0.5          # 0-1
    seed: int = 0
    scale_min: float = 0.7
    scale_max: float = 1.3
    rotation_min: float = 0.0
    rotation_max: float = 360.0
    spacing: float = 20.0
    variation: float = 0.5       # 0-1, randomness amount
    exclusion_zones: list[QRectF] = field(default_factory=list)
    respect_layers: bool = True
    asset_ids: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)  # probability per asset


@dataclass
class GenerationResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generator_type: GeneratorType = GeneratorType.FOREST
    params: GeneratorParams = field(default_factory=GeneratorParams)
    items: list[GeneratedItem] = field(default_factory=list)
    layer_id: Optional[str] = None


# ─── Generators ──────────────────────────────────────────────────────────────

class BaseGenerator:
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        raise NotImplementedError

    def _rng(self, seed: int) -> random.Random:
        return random.Random(seed)

    def _in_exclusion(self, point: QPointF, zones: list[QRectF]) -> bool:
        return any(z.contains(point) for z in zones)

    def _pick_asset(self, rng: random.Random, params: GeneratorParams) -> Optional[str]:
        if not params.asset_ids:
            return None
        if params.weights and len(params.weights) == len(params.asset_ids):
            return rng.choices(params.asset_ids, weights=params.weights, k=1)[0]
        return rng.choice(params.asset_ids)

    def _random_transform(self, rng: random.Random, params: GeneratorParams) -> tuple[float, float]:
        rot = rng.uniform(params.rotation_min, params.rotation_max)
        scale = rng.uniform(params.scale_min, params.scale_max)
        return rot, scale


class ForestGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        area = params.area
        step = params.spacing / max(0.1, params.density)
        x = area.x()
        while x < area.right():
            y = area.y()
            while y < area.bottom():
                jx = x + rng.uniform(-params.variation * step * 0.5, params.variation * step * 0.5)
                jy = y + rng.uniform(-params.variation * step * 0.5, params.variation * step * 0.5)
                pt = QPointF(jx, jy)
                if area.contains(pt) and not self._in_exclusion(pt, params.exclusion_zones):
                    rot, scale = self._random_transform(rng, params)
                    items.append(GeneratedItem(
                        asset_id=self._pick_asset(rng, params),
                        position=pt, rotation=rot, scale=scale,
                    ))
                y += step
            x += step
        return items


class MountainGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        area = params.area
        count = int(area.width() * area.height() * params.density / 5000)
        for _ in range(max(1, count)):
            pt = QPointF(rng.uniform(area.x(), area.right()),
                         rng.uniform(area.y(), area.bottom()))
            if self._in_exclusion(pt, params.exclusion_zones):
                continue
            rot, scale = self._random_transform(rng, params)
            scale *= 1.5  # mountains are bigger
            items.append(GeneratedItem(
                asset_id=self._pick_asset(rng, params),
                position=pt, rotation=rot * 0.1, scale=scale,
                z_offset=rng.uniform(0, 5),
            ))
        return items


class VillageGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        center = params.area.center()
        radius = min(params.area.width(), params.area.height()) / 2
        house_count = int(5 + params.density * 20)
        for i in range(house_count):
            angle = (2 * math.pi / house_count) * i + rng.uniform(-0.3, 0.3)
            dist = rng.uniform(radius * 0.2, radius * 0.8)
            pt = QPointF(center.x() + math.cos(angle) * dist,
                         center.y() + math.sin(angle) * dist)
            if self._in_exclusion(pt, params.exclusion_zones):
                continue
            rot, scale = self._random_transform(rng, params)
            items.append(GeneratedItem(
                asset_id=self._pick_asset(rng, params),
                position=pt, rotation=rot * 0.05, scale=scale,
            ))
        return items


class RockGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        area = params.area
        count = int(area.width() * area.height() * params.density / 3000)
        for _ in range(max(1, count)):
            pt = QPointF(rng.uniform(area.x(), area.right()),
                         rng.uniform(area.y(), area.bottom()))
            if self._in_exclusion(pt, params.exclusion_zones):
                continue
            rot, scale = self._random_transform(rng, params)
            items.append(GeneratedItem(
                asset_id=self._pick_asset(rng, params),
                position=pt, rotation=rot, scale=scale * 0.8,
            ))
        return items


class CloudGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        area = params.area
        count = int(3 + params.density * 10)
        for _ in range(count):
            pt = QPointF(rng.uniform(area.x(), area.right()),
                         rng.uniform(area.y(), area.bottom()))
            rot, scale = self._random_transform(rng, params)
            items.append(GeneratedItem(
                asset_id=self._pick_asset(rng, params),
                position=pt, rotation=rot * 0.02, scale=scale * 2.0,
                opacity=rng.uniform(0.3, 0.7),
            ))
        return items


class FogGenerator(BaseGenerator):
    def generate(self, params: GeneratorParams) -> list[GeneratedItem]:
        rng = self._rng(params.seed)
        items = []
        area = params.area
        count = int(5 + params.density * 15)
        for _ in range(count):
            pt = QPointF(rng.uniform(area.x(), area.right()),
                         rng.uniform(area.y(), area.bottom()))
            _, scale = self._random_transform(rng, params)
            items.append(GeneratedItem(
                asset_id=self._pick_asset(rng, params),
                position=pt, rotation=0, scale=scale * 3.0,
                opacity=rng.uniform(0.1, 0.4),
            ))
        return items


# ─── Procedural Engine ───────────────────────────────────────────────────────

class ProceduralEngine:
    def __init__(self):
        self._results: dict[str, GenerationResult] = {}
        self._generators: dict[GeneratorType, BaseGenerator] = {
            GeneratorType.FOREST: ForestGenerator(),
            GeneratorType.MOUNTAIN: MountainGenerator(),
            GeneratorType.VILLAGE: VillageGenerator(),
            GeneratorType.ROCK: RockGenerator(),
            GeneratorType.CLOUD: CloudGenerator(),
            GeneratorType.FOG: FogGenerator(),
        }

    def generate(self, gen_type: GeneratorType, params: GeneratorParams,
                 layer_id: str = None) -> GenerationResult:
        generator = self._generators[gen_type]
        items = generator.generate(params)
        result = GenerationResult(
            generator_type=gen_type, params=params,
            items=items, layer_id=layer_id,
        )
        self._results[result.id] = result
        return result

    def regenerate(self, result_id: str, new_seed: int = None) -> Optional[GenerationResult]:
        result = self._results.get(result_id)
        if not result:
            return None
        if new_seed is not None:
            result.params.seed = new_seed
        generator = self._generators[result.generator_type]
        result.items = generator.generate(result.params)
        return result

    def remove_result(self, result_id: str) -> Optional[GenerationResult]:
        return self._results.pop(result_id, None)

    def get_result(self, result_id: str) -> Optional[GenerationResult]:
        return self._results.get(result_id)

    def get_all_results(self) -> list[GenerationResult]:
        return list(self._results.values())

    def register_generator(self, gen_type: GeneratorType, generator: BaseGenerator):
        self._generators[gen_type] = generator

    @property
    def result_count(self) -> int:
        return len(self._results)
