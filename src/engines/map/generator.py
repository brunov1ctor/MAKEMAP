"""Map Generator — generates biome content inside polygon regions."""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPolygonF

from src.engines.map.point_distribution import (
    generate_points_in_polygon,
    distance_to_polygon_edge,
)
from src.engines.map.presets import GeneratorPreset, ObjectLayer
from src.engines.procedural import GeneratedItem


class MapGenerator:
    """Generates map objects inside a polygon using a preset configuration."""

    def generate_region(
        self,
        polygon: QPolygonF,
        preset: GeneratorPreset,
        seed: int = 0,
    ) -> list[GeneratedItem]:
        """Generate all object layers for a region."""
        items: list[GeneratedItem] = []

        for layer in preset.object_layers:
            layer_items = self._generate_layer(polygon, layer, preset, seed)
            items.extend(layer_items)
            seed += 1000  # offset seed per layer

        return items

    def _generate_layer(
        self,
        polygon: QPolygonF,
        layer: ObjectLayer,
        preset: GeneratorPreset,
        seed: int,
    ) -> list[GeneratedItem]:
        """Generate a single object layer within the polygon."""
        bounds = polygon.boundingRect()
        area = bounds.width() * bounds.height()
        count = int(area * layer.density / (layer.spacing * layer.spacing))
        count = max(1, count)

        points = generate_points_in_polygon(polygon, count, layer.spacing, seed)

        rng = random.Random(seed)
        items: list[GeneratedItem] = []

        for pt in points:
            # Edge falloff — reduce probability near borders
            edge_dist = distance_to_polygon_edge(pt, polygon)
            if edge_dist < preset.edge_softness:
                probability = edge_dist / preset.edge_softness
                if rng.random() > probability:
                    continue

            # Pick asset
            if not layer.asset_ids:
                continue
            asset_id = rng.choice(layer.asset_ids)

            # Random transform
            scale = rng.uniform(layer.scale_min, layer.scale_max)
            rotation = rng.uniform(0, 360)

            items.append(GeneratedItem(
                asset_id=asset_id,
                position=pt,
                scale=scale,
                rotation=rotation,
            ))

        return items
