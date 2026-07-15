"""Generator Presets — biome configurations for procedural map generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ObjectLayer:
    """A layer of objects within a biome preset."""
    category: str
    asset_ids: list[str] = field(default_factory=list)
    density: float = 0.3
    spacing: float = 40.0
    scale_min: float = 0.7
    scale_max: float = 1.3
    edge_falloff: float = 40.0  # distance from border where density drops


@dataclass
class GeneratorPreset:
    """Defines how a biome region is populated."""
    name: str
    ground_texture: str = ""
    object_layers: list[ObjectLayer] = field(default_factory=list)
    edge_softness: float = 40.0  # border transition width


# ─── Built-in Presets ────────────────────────────────────────────────────────

FOREST_PRESET = GeneratorPreset(
    name="Floresta Temperada",
    ground_texture="grass_base",
    object_layers=[
        ObjectLayer(
            category="large_trees",
            asset_ids=["tree_oak_01", "tree_oak_02"],
            density=0.20,
            spacing=55,
            scale_min=0.8,
            scale_max=1.3,
        ),
        ObjectLayer(
            category="small_trees",
            asset_ids=["tree_small_01", "tree_small_02"],
            density=0.40,
            spacing=30,
            scale_min=0.6,
            scale_max=1.0,
        ),
        ObjectLayer(
            category="rocks",
            asset_ids=["rock_01", "rock_02"],
            density=0.05,
            spacing=50,
            scale_min=0.5,
            scale_max=1.0,
        ),
    ],
    edge_softness=50.0,
)

MOUNTAIN_PRESET = GeneratorPreset(
    name="Montanhas",
    ground_texture="rock_base",
    object_layers=[
        ObjectLayer(
            category="mountains",
            asset_ids=["mountain_01", "mountain_02"],
            density=0.10,
            spacing=80,
            scale_min=0.9,
            scale_max=1.5,
        ),
        ObjectLayer(
            category="rocks",
            asset_ids=["rock_01", "rock_02", "rock_03"],
            density=0.15,
            spacing=35,
            scale_min=0.4,
            scale_max=1.0,
        ),
    ],
    edge_softness=30.0,
)

VILLAGE_PRESET = GeneratorPreset(
    name="Vila",
    ground_texture="sand_base",
    object_layers=[
        ObjectLayer(
            category="buildings",
            asset_ids=["house_01", "tower_01"],
            density=0.12,
            spacing=60,
            scale_min=0.9,
            scale_max=1.1,
        ),
    ],
    edge_softness=20.0,
)

DESERT_PRESET = GeneratorPreset(
    name="Deserto",
    ground_texture="sand_base",
    object_layers=[
        ObjectLayer(
            category="rocks",
            asset_ids=["rock_01", "rock_02"],
            density=0.03,
            spacing=70,
            scale_min=0.5,
            scale_max=1.2,
        ),
    ],
    edge_softness=60.0,
)

PRESETS: dict[str, GeneratorPreset] = {
    "forest": FOREST_PRESET,
    "mountain": MOUNTAIN_PRESET,
    "village": VILLAGE_PRESET,
    "desert": DESERT_PRESET,
}
