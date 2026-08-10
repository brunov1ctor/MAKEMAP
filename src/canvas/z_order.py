"""Single source of truth for QGraphicsItem stacking order (zValue) on the
main map canvas — terrain, water/roads, zones, grid, planted objects (assets/
mobs/npcs), lighting, tool chrome, all the way up to the transform gizmo.

Before this existed, each layer picked its own zValue literal locally and
documented its neighbors in a comment (e.g. "above terrain (1), below
stamped objects (10+)"). That works until two call sites that both mention
each other get edited independently — which is exactly what happened: an
asset/mob stamp's zValue moved from 0.5 to 10 (fixing stamps rendering
under terrain) without GlobalLightingOverlay's zValue (8) moving with it,
silently hiding every occluder shadow/contact smudge underneath the stamps
it was supposed to darken. One shared enum means editing a tier's neighbors
happens in the same file, in the same diff.

Values are today's literal zValue x10 — same relative order as before, but
with a gap of 10 between neighboring tiers so a new layer can be inserted
without renumbering anything else (e.g. a tier between GRID_LINES=90 and
STAMPED_OBJECT=100 becomes 95).

Scenes that don't share this space — the skill-tree and world-progression
mini node-graph editors (layouts/panels/items/skill_tree/items.py,
layouts/panels/progression/items.py) each own a private QGraphicsScene and
keep their own small local zValues; they're not part of this enum."""

from __future__ import annotations

from enum import IntEnum


class ZOrder(IntEnum):
    BOUNDARY_OUTLINE = -10       # map_boundary.py: the movable boundary outline path itself
    BOUNDARY_GROUP = 0           # map_boundary.py: the boundary's stable container group
    TERRAIN = 10                 # terrain_layer.py: painted terrain
    SHORELINE_BLEND = 15         # shoreline_blend.py: foam/shoreline-blend overlay
    ANIMATED_EFFECTS = 60        # brush_effects_overlay.py: brush-painted Névoa/fog etc.
    ZONE_FILL = 50               # engine.py paint_zone: zone/region tint fill
    RIVER_PATH = 70              # path_item.py: RiverPathItem
    ROAD_PATH = 80               # path_item.py: RoadPathItem
    REGION_FILL = 85             # region_layer.py: região fill/border
    REGION_LABEL = 87            # region_layer.py: região name/star-rating label
    GRID_LINES = 90              # grid.py: main grid line group
    GRID_MEASURE = 91            # grid.py: measurement/ruler overlay group
    STAMPED_OBJECT = 100         # brush_tool/spawn_tool stamps + procedural generation results
    LIGHTING_OVERLAY = 110       # lighting_overlay.py: GlobalLightingOverlay (glow/shadows/haze)
    TOOL_PREVIEW = 500           # dashed live-drawing previews (region/road/river), placed
                                  # TextItem, NeonPreviewOverlay's boundary-edit highlight
    PROGRESSION_CONNECTOR = 570  # progression/map_overlay.py: _ConnectorLine between cards
    PROGRESSION_PIN = 580        # progression/map_overlay.py: _MapMarkerItem (just under real markers)
    PLACED_GIZMO = 600           # MarkerItem, LightItem, VertexHandlesOverlay's drag handles
    TRANSFORM_ITEM_BORDER = 99980   # transform.py: per-item outline (multi-select)
    TRANSFORM_GROUP_BORDER = 99990  # transform.py: group selection-bounds border
    CURSOR_GHOST = 99990         # tool cursor ghosts, alignment guides, box/lasso select,
                                  # locate-pin "ping" rings — always-on-top transient chrome
    TRANSFORM_HANDLE = 100000    # transform.py: resize/rotate handle dot
    TRANSFORM_LABEL = 100010     # transform.py: glyph label on an action button
