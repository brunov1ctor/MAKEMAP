"""Migration runner — versioned schema management."""

from __future__ import annotations

import logging
from src.database.connection import Database

logger = logging.getLogger("MAKEMAP")

# Each migration is (version, description, sql)
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "Initial schema", """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );

        -- World
        CREATE TABLE IF NOT EXISTS worlds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            settings TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Continents
        CREATE TABLE IF NOT EXISTS continents (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Kingdoms
        CREATE TABLE IF NOT EXISTS kingdoms (
            id TEXT PRIMARY KEY,
            continent_id TEXT NOT NULL REFERENCES continents(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#FFFFFF',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Regions
        CREATE TABLE IF NOT EXISTS regions (
            id TEXT PRIMARY KEY,
            kingdom_id TEXT REFERENCES kingdoms(id) ON DELETE SET NULL,
            world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            level_min INTEGER DEFAULT 1,
            level_max INTEGER DEFAULT 1,
            biome TEXT DEFAULT '',
            music TEXT DEFAULT '',
            danger INTEGER DEFAULT 1,
            color TEXT DEFAULT '#FFFFFF',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Biomes
        CREATE TABLE IF NOT EXISTS biomes (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#228B22',
            temperature TEXT DEFAULT 'temperate',
            humidity TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Cities
        CREATE TABLE IF NOT EXISTS cities (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            city_type TEXT DEFAULT 'city',
            population INTEGER DEFAULT 0,
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- NPCs
        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY,
            city_id TEXT REFERENCES cities(id) ON DELETE SET NULL,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            role TEXT DEFAULT '',
            faction TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            dialogue TEXT DEFAULT '',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Mobs
        CREATE TABLE IF NOT EXISTS mobs (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            race TEXT DEFAULT '',
            element TEXT DEFAULT '',
            faction TEXT DEFAULT '',
            health INTEGER DEFAULT 100,
            damage INTEGER DEFAULT 10,
            defense INTEGER DEFAULT 5,
            respawn_time INTEGER DEFAULT 60,
            patrol_radius REAL DEFAULT 10,
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Bosses
        CREATE TABLE IF NOT EXISTS bosses (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            dungeon_id TEXT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            boss_type TEXT DEFAULT 'boss',
            health INTEGER DEFAULT 10000,
            phases INTEGER DEFAULT 1,
            mechanics TEXT DEFAULT '[]',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Items
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            item_type TEXT DEFAULT 'misc',
            rarity TEXT DEFAULT 'common',
            level_req INTEGER DEFAULT 1,
            stats TEXT DEFAULT '{}',
            icon TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Resources
        CREATE TABLE IF NOT EXISTS resources (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            resource_type TEXT DEFAULT 'ore',
            respawn_time INTEGER DEFAULT 300,
            quantity INTEGER DEFAULT 1,
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Quests
        CREATE TABLE IF NOT EXISTS quests (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            chain_id TEXT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            quest_type TEXT DEFAULT 'main',
            level_req INTEGER DEFAULT 1,
            objectives TEXT DEFAULT '[]',
            rewards TEXT DEFAULT '[]',
            chain_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Quest Chains
        CREATE TABLE IF NOT EXISTS quest_chains (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Dungeons
        CREATE TABLE IF NOT EXISTS dungeons (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            level_min INTEGER DEFAULT 1,
            level_max INTEGER DEFAULT 1,
            difficulty TEXT DEFAULT 'normal',
            rooms INTEGER DEFAULT 1,
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Events
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_type TEXT DEFAULT 'world',
            trigger_condition TEXT DEFAULT '',
            duration INTEGER DEFAULT 0,
            recurring INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Factions
        CREATE TABLE IF NOT EXISTS factions (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#FFFFFF',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Tags
        CREATE TABLE IF NOT EXISTS tags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#FFFFFF'
        );

        -- N:N entity_tags
        CREATE TABLE IF NOT EXISTS entity_tags (
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (entity_id, entity_type, tag_id)
        );

        -- N:N relationships
        CREATE TABLE IF NOT EXISTS entity_relationships (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            relationship_type TEXT DEFAULT 'related'
        );

        -- Mob drops (N:N mobs <-> items)
        CREATE TABLE IF NOT EXISTS mob_drops (
            mob_id TEXT NOT NULL REFERENCES mobs(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            drop_rate REAL DEFAULT 0.1,
            quantity_min INTEGER DEFAULT 1,
            quantity_max INTEGER DEFAULT 1,
            PRIMARY KEY (mob_id, item_id)
        );

        -- Boss drops
        CREATE TABLE IF NOT EXISTS boss_drops (
            boss_id TEXT NOT NULL REFERENCES bosses(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            drop_rate REAL DEFAULT 0.1,
            quantity_min INTEGER DEFAULT 1,
            quantity_max INTEGER DEFAULT 1,
            PRIMARY KEY (boss_id, item_id)
        );

        -- Quest NPCs (N:N)
        CREATE TABLE IF NOT EXISTS quest_npcs (
            quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            role TEXT DEFAULT 'giver',
            PRIMARY KEY (quest_id, npc_id)
        );

        -- Quest Mobs (N:N)
        CREATE TABLE IF NOT EXISTS quest_mobs (
            quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
            mob_id TEXT NOT NULL REFERENCES mobs(id) ON DELETE CASCADE,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (quest_id, mob_id)
        );

        -- Quest Items (N:N)
        CREATE TABLE IF NOT EXISTS quest_items (
            quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            role TEXT DEFAULT 'reward',
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (quest_id, item_id)
        );

        -- Maps
        CREATE TABLE IF NOT EXISTS maps (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            parent_map_id TEXT REFERENCES maps(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            map_type TEXT DEFAULT 'world',
            width INTEGER DEFAULT 4096,
            height INTEGER DEFAULT 4096,
            background_asset_id TEXT,
            settings TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Layers
        CREATE TABLE IF NOT EXISTS layers (
            id TEXT PRIMARY KEY,
            map_id TEXT NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            layer_order INTEGER DEFAULT 0,
            visible INTEGER DEFAULT 1,
            locked INTEGER DEFAULT 0,
            opacity REAL DEFAULT 1.0,
            blend_mode TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Canvas Items
        CREATE TABLE IF NOT EXISTS canvas_items (
            id TEXT PRIMARY KEY,
            map_id TEXT NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            layer_id TEXT NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
            item_type TEXT NOT NULL,
            entity_id TEXT,
            entity_type TEXT,
            asset_id TEXT,
            name TEXT DEFAULT '',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            rotation REAL DEFAULT 0,
            scale_x REAL DEFAULT 1,
            scale_y REAL DEFAULT 1,
            opacity REAL DEFAULT 1,
            z_index INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0,
            visible INTEGER DEFAULT 1,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Assets
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            pack_id TEXT,
            name TEXT NOT NULL,
            asset_type TEXT DEFAULT 'image',
            source_path TEXT DEFAULT '',
            thumbnail_path TEXT DEFAULT '',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            pivot_x REAL DEFAULT 0.5,
            pivot_y REAL DEFAULT 0.5,
            default_scale REAL DEFAULT 1.0,
            category TEXT DEFAULT '',
            author TEXT DEFAULT '',
            license TEXT DEFAULT '',
            hash TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Asset Packs
        CREATE TABLE IF NOT EXISTS asset_packs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            author TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Asset Settings (per-project overrides: brightness, contrast, volumes)
        CREATE TABLE IF NOT EXISTS asset_settings (
            asset_id TEXT PRIMARY KEY,
            brightness REAL DEFAULT 0.0,
            contrast REAL DEFAULT 0.0,
            sound_volume_paint REAL DEFAULT 0.7,
            sound_volume_ambient REAL DEFAULT 0.7
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_regions_world ON regions(world_id);
        CREATE INDEX IF NOT EXISTS idx_regions_kingdom ON regions(kingdom_id);
        CREATE INDEX IF NOT EXISTS idx_mobs_region ON mobs(region_id);
        CREATE INDEX IF NOT EXISTS idx_npcs_region ON npcs(region_id);
        CREATE INDEX IF NOT EXISTS idx_quests_region ON quests(region_id);
        CREATE INDEX IF NOT EXISTS idx_cities_region ON cities(region_id);
        CREATE INDEX IF NOT EXISTS idx_dungeons_region ON dungeons(region_id);
        CREATE INDEX IF NOT EXISTS idx_canvas_items_map ON canvas_items(map_id);
        CREATE INDEX IF NOT EXISTS idx_canvas_items_layer ON canvas_items(layer_id);
        CREATE INDEX IF NOT EXISTS idx_layers_map ON layers(map_id);
        CREATE INDEX IF NOT EXISTS idx_entity_tags_entity ON entity_tags(entity_id, entity_type);
    """),
    (2, "Painted zones (Região panel — brush-painted colored areas)", """
        -- map_id is a plain tag, not a FK to maps(id): the maps/worlds
        -- hierarchy has no creation flow wired up anywhere yet, and
        -- painted zones shouldn't be blocked on that unrelated feature.
        CREATE TABLE IF NOT EXISTS painted_zones (
            id TEXT PRIMARY KEY,
            map_id TEXT NOT NULL DEFAULT 'default',
            category_key TEXT NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            mask_png TEXT NOT NULL DEFAULT '',
            mask_x REAL DEFAULT 0,
            mask_y REAL DEFAULT 0,
            stars INTEGER DEFAULT 0,
            estilo TEXT DEFAULT 'Nenhum',
            observacao TEXT DEFAULT '',
            visible INTEGER DEFAULT 1,
            brush_radius REAL DEFAULT 50,
            brush_softness REAL DEFAULT 0.5,
            brush_opacity REAL DEFAULT 0.5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_painted_zones_map ON painted_zones(map_id);
    """),
    (3, "Mobs panel — extended creature fields", """
        ALTER TABLE mobs ADD COLUMN category TEXT DEFAULT 'outros';
        ALTER TABLE mobs ADD COLUMN subcategory TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN tier INTEGER DEFAULT 1;
        ALTER TABLE mobs ADD COLUMN rarity TEXT DEFAULT 'normal';
        ALTER TABLE mobs ADD COLUMN zone_id TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN mana INTEGER DEFAULT 50;
        ALTER TABLE mobs ADD COLUMN velocidade REAL DEFAULT 100;
        ALTER TABLE mobs ADD COLUMN critico REAL DEFAULT 5;
        ALTER TABLE mobs ADD COLUMN esquiva REAL DEFAULT 5;
        ALTER TABLE mobs ADD COLUMN precisao REAL DEFAULT 90;
        ALTER TABLE mobs ADD COLUMN ai_type TEXT DEFAULT 'Agressivo';
        ALTER TABLE mobs ADD COLUMN comportamento TEXT DEFAULT 'Territorial';
        ALTER TABLE mobs ADD COLUMN alinhamento TEXT DEFAULT 'Neutro';
        ALTER TABLE mobs ADD COLUMN resistances TEXT DEFAULT '{}';
        ALTER TABLE mobs ADD COLUMN abilities_notes TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN spawn_notes TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN animation_notes TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN effect_notes TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN notes TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN drops_json TEXT DEFAULT '[]';
        ALTER TABLE mobs ADD COLUMN image_path TEXT DEFAULT '';
        ALTER TABLE mobs ADD COLUMN favorite INTEGER DEFAULT 0;
        CREATE INDEX IF NOT EXISTS idx_mobs_category ON mobs(category);
        CREATE INDEX IF NOT EXISTS idx_mobs_zone ON mobs(zone_id);
    """),
    (4, "Mobs panel — status, economy and physical/magic resist fields", """
        ALTER TABLE mobs ADD COLUMN status TEXT DEFAULT 'ativo';
        ALTER TABLE mobs ADD COLUMN peso REAL DEFAULT 0;
        ALTER TABLE mobs ADD COLUMN xp INTEGER DEFAULT 0;
        ALTER TABLE mobs ADD COLUMN ouro INTEGER DEFAULT 0;
        ALTER TABLE mobs ADD COLUMN tamanho TEXT DEFAULT 'Médio';
        ALTER TABLE mobs ADD COLUMN resist_fisica REAL DEFAULT 0;
        ALTER TABLE mobs ADD COLUMN resist_magica REAL DEFAULT 0;
    """),
    (5, "Mobs panel — category folders (directory-style tree, replaces the flat CATEGORY_DEFS list)", """
        -- Self-referencing tree: parent_id NULL means a root-level folder.
        -- No FK from mobs.category into this table on purpose — mobs.category
        -- was already a loose TEXT tag with no FK (see migration 3), same
        -- reasoning as painted_zones.map_id in migration 2: a mob whose
        -- folder gets deleted shouldn't become impossible to load, it just
        -- falls back to "outros" in the UI.
        CREATE TABLE IF NOT EXISTS mob_categories (
            id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES mob_categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🐾',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mob_categories_parent ON mob_categories(parent_id);

        -- Seed with the old fixed CATEGORY_DEFS list as root folders, using
        -- the same ids that used to be the flat category keys — every
        -- existing mob's `category` value keeps resolving to the same
        -- folder without any data migration on the mobs table itself.
        INSERT OR IGNORE INTO mob_categories (id, parent_id, name, icon, sort_order) VALUES
            ('npc_hostil', NULL, 'NPC Hostil', '☠', 0),
            ('animais', NULL, 'Animais', '🐺', 1),
            ('mortos_vivos', NULL, 'Mortos-vivos', '🧟', 2),
            ('maquinas', NULL, 'Máquinas', '🤖', 3),
            ('humanoides', NULL, 'Humanoides', '🧑‍🤝‍🧑', 4),
            ('dragoes', NULL, 'Dragões', '🐉', 5),
            ('insetos', NULL, 'Insetos', '🐛', 6),
            ('aquaticos', NULL, 'Aquáticos', '🐊', 7),
            ('elementais', NULL, 'Elementais', '🔥', 8),
            ('plantas', NULL, 'Plantas', '🌿', 9),
            ('demoniacos', NULL, 'Demoníacos', '👹', 10),
            ('outros', NULL, 'Outros', '❔', 11);
    """),
    (6, "Mobs panel — Tipo (relação com o jogador) and Ambiente (bioma) fields", """
        ALTER TABLE mobs ADD COLUMN tipo TEXT DEFAULT 'Inimigo';
        ALTER TABLE mobs ADD COLUMN ambiente TEXT DEFAULT '';
    """),
    (7, "Mobs panel — Chefes (Boss) and Elite become real navigable category folders instead of computed-rarity smart filters; drops the previous fixed creature-family seed categories", """
        -- The 12 creature-family categories from migration 5 are gone —
        -- the user hadn't created any mobs yet, so nothing references
        -- them, and they want to build their own category tree from
        -- scratch starting with just Chefes (Boss) and Elite as roots
        -- (matching Favoritos/Chefes/Elite in the explorer's reference
        -- design). ON DELETE CASCADE (migration 5) takes any subfolders
        -- created under them along too.
        DELETE FROM mob_categories WHERE id IN (
            'npc_hostil', 'animais', 'mortos_vivos', 'maquinas', 'humanoides',
            'dragoes', 'insetos', 'aquaticos', 'elementais', 'plantas',
            'demoniacos', 'outros'
        );
        -- Chefes (Boss) and Elite move from SMART_FILTERS (categories.py,
        -- computed from mobs.rarity) into the folder tree proper — a mob
        -- filed under one is now assigned via its Categoria field like
        -- any other folder, not automatically via Raridade. Todos and
        -- Favoritos stay pinned smart filters (not folders): "Todos" is
        -- just the root view, and "favorite" is a per-mob flag, not a
        -- hierarchical grouping.
        INSERT OR IGNORE INTO mob_categories (id, parent_id, name, icon, sort_order) VALUES
            ('chefes_boss', NULL, 'Chefes (Boss)', '👑', 0),
            ('elite', NULL, 'Elite', '💠', 1);
    """),
    (8, "Mobs panel — Informações Extras redesign: Drops link to the Item catalog, Habilidades becomes a structured list, and mobs get a real Assets list (map-stamp source, see mob_assets)", """
        -- Drops Principais now reference a real items row (icon/rarity
        -- come from there) instead of a bare typed-in name — drops_json
        -- entries become {item_id, rate, qty} at the application level;
        -- no schema change needed for that column itself since it was
        -- already free-form JSON TEXT.
        ALTER TABLE items ADD COLUMN image_path TEXT DEFAULT '';

        -- Habilidades moves from one free-text notes box to a structured
        -- list (name/description/rarity per entry) — abilities_notes
        -- stays in place (harmless, unread by the new UI) rather than
        -- being dropped, since SQLite can't cheaply drop a column and
        -- nothing depends on it being gone.
        ALTER TABLE mobs ADD COLUMN abilities_json TEXT DEFAULT '[]';

        -- One mob can have several stamp assets (e.g. alternate
        -- skins/poses) — a real table rather than a JSON blob on mobs
        -- because each entry needs its own identity (the eventual
        -- toolbar "Mobs" placement tool will reference a specific
        -- mob_assets.id, not just "this mob"). No FK into the separate
        -- asset-library SQLite database (library/library.sqlite) — that
        -- store is intentionally project-independent, same reasoning as
        -- mobs.category having no FK to mob_categories.
        CREATE TABLE IF NOT EXISTS mob_assets (
            id TEXT PRIMARY KEY,
            mob_id TEXT NOT NULL REFERENCES mobs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            asset_type TEXT DEFAULT 'Modelo 3D',
            file_path TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            rarity TEXT DEFAULT 'common',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mob_assets_mob ON mob_assets(mob_id);
    """),
    (9, "Mobs panel — drop the example category folders (Chefes (Boss) / Elite) seeded by migration 7", """
        -- Those two were only ever meant as a starting example; the user
        -- wants the category tree empty by default and to build their
        -- own from scratch, same reasoning as migration 7 dropping the
        -- previous 12-folder seed list. Any mob already filed under
        -- either one keeps its `category` value (no FK — see migration
        -- 5's comment) and just falls back to the edit panel's
        -- "Sem categoria" placeholder instead of losing the field.
        DELETE FROM mob_categories WHERE id IN ('chefes_boss', 'elite');
    """),
    (10, "Brush tool persistence — painted terrain masks + reusable canvas_items for object stamps", """
        -- Terrain material painting (BrushTool, distinct from the Região
        -- panel's own painted_zones) had no persistence at all — strokes
        -- only ever lived in the live QGraphicsScene, so switching
        -- projects left the previous project's painting visible in the
        -- new one. Mirrors painted_zones: map_id is a plain tag, not a FK
        -- (same reasoning — the maps/worlds hierarchy isn't wired up).
        CREATE TABLE IF NOT EXISTS painted_terrain (
            id TEXT PRIMARY KEY,
            map_id TEXT DEFAULT 'default',
            asset_id TEXT NOT NULL,
            mask_png TEXT NOT NULL DEFAULT '',
            mask_x REAL DEFAULT 0,
            mask_y REAL DEFAULT 0,
            texture_scale REAL DEFAULT 1,
            texture_rotation REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_painted_terrain_map ON painted_terrain(map_id);

        -- canvas_items (migration 1) has sat completely unused since it
        -- was first created — no code anywhere ever inserted into it —
        -- because its hard FKs to maps(id)/layers(id) require a
        -- maps/layers hierarchy that was never wired up (same gap
        -- painted_zones already worked around). Recreating it here is
        -- safe (nothing to migrate out of it) and lets brush-tool object
        -- stamps use it the same loose-tag way painted_zones/
        -- painted_terrain do.
        DROP TABLE IF EXISTS canvas_items;
        CREATE TABLE canvas_items (
            id TEXT PRIMARY KEY,
            map_id TEXT NOT NULL DEFAULT 'default',
            layer_id TEXT NOT NULL DEFAULT 'default',
            item_type TEXT NOT NULL,
            entity_id TEXT,
            entity_type TEXT,
            asset_id TEXT,
            name TEXT DEFAULT '',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            rotation REAL DEFAULT 0,
            scale_x REAL DEFAULT 1,
            scale_y REAL DEFAULT 1,
            opacity REAL DEFAULT 1,
            z_index INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0,
            visible INTEGER DEFAULT 1,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_canvas_items_map ON canvas_items(map_id);
        CREATE INDEX IF NOT EXISTS idx_canvas_items_layer ON canvas_items(layer_id);
    """),
    (11, "Terrain panel persistence — map boundaries (shape/size/position/visibility) per project", """
        -- TerrainMediator kept every terrain boundary only in memory
        -- (self._boundaries), so switching projects left the previous
        -- project's terrains visible in the new one — same class of bug
        -- migration 10 fixed for Brush painting, and worse here since
        -- Região/Brush both resolve a terrain_id against these boundaries
        -- to constrain their own painting. map_id is a plain tag, not a
        -- FK, same reasoning as painted_zones/painted_terrain.
        CREATE TABLE IF NOT EXISTS terrains (
            id TEXT PRIMARY KEY,
            map_id TEXT DEFAULT 'default',
            name TEXT NOT NULL,
            shape TEXT DEFAULT 'rectangle',
            width INTEGER DEFAULT 4096,
            height INTEGER DEFAULT 4096,
            color TEXT DEFAULT '',
            position_x REAL DEFAULT 0,
            position_y REAL DEFAULT 0,
            visible INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_terrains_map ON terrains(map_id);

        -- painted_zones has tracked "which terrain a região is painted
        -- within" in memory (RegionMediator._Zone.terrain_id) since it was
        -- first built, but this column was never added, so the
        -- association silently reset on every reload.
        ALTER TABLE painted_zones ADD COLUMN terrain_id TEXT DEFAULT '';
    """),
    (12, "Itens e Habilidades panel — extend items with editor fields, add skills + skill_trees", """
        -- The Itens/Habilidades screen (ItemsSkillsPanel) needs a handful
        -- of first-class columns the old `items` row didn't carry. Most of
        -- the editor's numeric fields (peso, valor, durabilidade, dano,
        -- flags, tags, …) live in the free-form `stats` JSON blob that was
        -- always there; only the ones worth filtering/sorting by in the
        -- list column get real columns here. `code` is the human-facing id
        -- shown in the editor header ("ITM_1001") — distinct from the uuid
        -- primary key, same split skills use below.
        ALTER TABLE items ADD COLUMN code TEXT DEFAULT '';
        ALTER TABLE items ADD COLUMN subcategory TEXT DEFAULT '';
        ALTER TABLE items ADD COLUMN favorite INTEGER DEFAULT 0;

        -- Skills (Habilidades) — brand new. Mirrors the items shape: a few
        -- real columns for the list/filters, everything else (área, alcance,
        -- durações, custos secundários, flags) in the `stats` JSON blob so
        -- the editor's tabs can grow without a migration each time.
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            code TEXT DEFAULT '',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'Ataque',
            rarity TEXT DEFAULT 'common',
            level INTEGER DEFAULT 1,
            cooldown REAL DEFAULT 0,
            mana_cost INTEGER DEFAULT 0,
            element TEXT DEFAULT '',
            stats TEXT DEFAULT '{}',
            icon TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            favorite INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);

        -- Árvore de Habilidades — one row per element tab (Fogo/Terra/Água/…).
        -- The whole node graph for that tab (nodes with positions, ranks and
        -- their connections) is stored as a single JSON document in `data`,
        -- same loose-tag philosophy painted_zones/canvas_items use: the tree
        -- is a UI layout artifact, not something other tables FK into, so a
        -- self-contained blob keyed by tab is the least-friction store.
        CREATE TABLE IF NOT EXISTS skill_trees (
            tree_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🔥',
            sort_order INTEGER DEFAULT 0,
            data TEXT DEFAULT '{\"nodes\": [], \"edges\": []}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """),
    (13, "Dungeons e Construções panel — buildings (base) table + dungeon editor fields", """
        -- Construções da base. Mesma divisão que items/skills usam: colunas
        -- reais só para o que a lista filtra/ordena e para o que a árvore de
        -- progressão precisa ler (tier/parent_id/status); o resto — custos,
        -- requisitos, produção, imagens de destaque — vai em blobs JSON, para
        -- as seções do editor crescerem sem uma migration a cada campo novo.
        CREATE TABLE IF NOT EXISTS buildings (
            id TEXT PRIMARY KEY,
            code TEXT DEFAULT '',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'Produção',
            subcategory TEXT DEFAULT '',
            icon TEXT DEFAULT '',
            image TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 5,
            build_time TEXT DEFAULT '00:00:00',
            structure TEXT DEFAULT 'Simples',
            -- Posição na árvore de progressão: o tier é a linha, parent_id a
            -- aresta que liga esta construção à que a destrava.
            tier INTEGER DEFAULT 1,
            parent_id TEXT REFERENCES buildings(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'disponivel',
            sort_order INTEGER DEFAULT 0,
            costs TEXT DEFAULT '[]',
            requirements TEXT DEFAULT '[]',
            visuals TEXT DEFAULT '[]',
            production TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_buildings_parent ON buildings(parent_id);

        -- Dungeons já existiam desde a migration 1 com o mínimo (nome,
        -- faixa de nível, dificuldade, salas). O editor da tela nova pede
        -- bastante coisa a mais; mesma regra de blob para listas.
        ALTER TABLE dungeons ADD COLUMN code TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN dungeon_type TEXT DEFAULT 'Exploração';
        ALTER TABLE dungeons ADD COLUMN image TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN est_time TEXT DEFAULT '00:00';
        ALTER TABLE dungeons ADD COLUMN group_min INTEGER DEFAULT 1;
        ALTER TABLE dungeons ADD COLUMN group_max INTEGER DEFAULT 4;
        ALTER TABLE dungeons ADD COLUMN biome TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN floors INTEGER DEFAULT 1;
        ALTER TABLE dungeons ADD COLUMN generation TEXT DEFAULT 'Linear';
        ALTER TABLE dungeons ADD COLUMN checkpoints INTEGER DEFAULT 0;
        ALTER TABLE dungeons ADD COLUMN secret_rooms INTEGER DEFAULT 0;
        ALTER TABLE dungeons ADD COLUMN rewards TEXT DEFAULT '[]';
        ALTER TABLE dungeons ADD COLUMN encounters TEXT DEFAULT '[]';
        ALTER TABLE dungeons ADD COLUMN bosses TEXT DEFAULT '[]';
        ALTER TABLE dungeons ADD COLUMN modifiers TEXT DEFAULT '{}';
        ALTER TABLE dungeons ADD COLUMN req_level INTEGER DEFAULT 1;
        ALTER TABLE dungeons ADD COLUMN req_quest TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN req_item TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN active INTEGER DEFAULT 1;
        ALTER TABLE dungeons ADD COLUMN visible_on_map INTEGER DEFAULT 1;
        ALTER TABLE dungeons ADD COLUMN group_available INTEGER DEFAULT 0;
        -- Telemetria exibida em "Informações Adicionais" — preenchida por
        -- quem integrar o jogo; a tela só lê.
        ALTER TABLE dungeons ADD COLUMN success_rate REAL DEFAULT 0;
        ALTER TABLE dungeons ADD COLUMN completions INTEGER DEFAULT 0;
        ALTER TABLE dungeons ADD COLUMN best_time TEXT DEFAULT '';
        ALTER TABLE dungeons ADD COLUMN attempts INTEGER DEFAULT 0;
    """),
    (14, "Dungeons e Construções panel — customizable category/type tabs", """
        -- Abas editáveis (criar/renomear/excluir) para o filtro de
        -- Categoria (Construções) e Tipo (Dungeons), substituindo as
        -- listas fixas que viviam só no código. Flat (sem parent_id) —
        -- ao contrário de mob_categories, aqui não há necessidade de
        -- pastas aninhadas, só uma fileira de abas.
        --
        -- buildings.category / dungeons.dungeon_type continuam TEXT livre
        -- (sem FK) guardando o NOME da aba, não um id — mesma filosofia
        -- que mobs.category já usa: renomear faz um UPDATE em cascata
        -- pelo nome antigo, excluir uma aba não apaga nem desvincula
        -- construções/dungeons já existentes, elas só ficam com um nome
        -- que não corresponde a nenhuma aba atual (mesmo comportamento
        -- que uma categoria de mob excluída já tem).
        CREATE TABLE IF NOT EXISTS building_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🏛',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS dungeon_types (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🕳',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Seed com as mesmas categorias/tipos que o painel já semeava via
        -- Templates, para quem já tem construções/dungeons continuar
        -- vendo as mesmas abas depois da migração.
        INSERT OR IGNORE INTO building_categories (id, name, icon, sort_order) VALUES
            ('producao', 'Produção', '⚒', 0),
            ('defesa', 'Defesa', '🛡', 1),
            ('militar', 'Militar', '⚔', 2),
            ('pesquisa', 'Pesquisa', '🔬', 3),
            ('armazenamento', 'Armazenamento', '📦', 4),
            ('social', 'Social', '🏘', 5),
            ('especial', 'Especial', '🌟', 6);
        INSERT OR IGNORE INTO dungeon_types (id, name, icon, sort_order) VALUES
            ('exploracao', 'Exploração', '🗺', 0),
            ('confronto', 'Confronto', '⚔', 1),
            ('enigma', 'Enigma', '🧩', 2),
            ('sobrevivencia', 'Sobrevivência', '🔥', 3),
            ('raide', 'Raide', '🐉', 4),
            ('evento', 'Evento', '🎆', 5);
    """),
    (15, "Habilidades — campo Evoluir de (progressão), substituindo o '+ Nó' manual da árvore", """
        -- A Árvore de Habilidades deixou de ser um canvas de posicionamento
        -- livre (arrastar da lista, clique duplo, "+ Nó — buscar
        -- habilidade") — os nós agora só existem como visualização do que
        -- o Editor de Habilidade já descreve. "Evoluir de" é a mesma ideia
        -- do "Desbloqueada por" das Construções: a própria habilidade
        -- referencia sua pré-requisito, e o par nó+aresta é derivado disso
        -- automaticamente.
        ALTER TABLE skills ADD COLUMN evolves_from TEXT REFERENCES skills(id) ON DELETE SET NULL;
    """),
    (16, "Mobs panel — seed the 5 difficulty-tier category folders (Normal/Raro/Elite/Épico/Boss) with mob-themed icons instead of the generic folder glyph", """
        -- The category tree (migration 5) has been empty by default since
        -- migration 9 dropped the old example seed — new users had to
        -- build every folder by hand, and freshly created ones defaulted
        -- to a plain 📁 icon (see panel_category_mixin.py's
        -- _confirm_new_category) that reads as "folder", not "mob". These
        -- 5 match the reference design's difficulty ladder and use icons
        -- that actually evoke that ladder instead.
        INSERT OR IGNORE INTO mob_categories (id, parent_id, name, icon, sort_order) VALUES
            ('normal', NULL, 'Normal', '🐾', 0),
            ('raro', NULL, 'Raro', '💎', 1),
            ('elite', NULL, 'Elite', '💠', 2),
            ('epico', NULL, 'Épico', '⚔️', 3),
            ('boss', NULL, 'Boss', '👑', 4);
    """),
    (17, "Mobs panel — backfill mobs stuck on the dead 'outros' category default to the new Normal folder", """
        -- mobs.category's DB column default has been the literal string
        -- 'outros' since migration 3, but that seeded folder was dropped
        -- in migration 7 — every mob that never had a category explicitly
        -- set was showing "❔ Sem categoria" in the editor/badge instead
        -- of a real folder. Migration 16 gives every project a "Normal"
        -- folder to fall back to instead; this backfills existing rows
        -- to match (mirrors edit_overview_mixin.py's own load()-time
        -- fallback, which now also treats 'outros' as unset for mobs
        -- created before this migration ran).
        UPDATE mobs SET category = 'normal' WHERE category = 'outros' OR category IS NULL OR category = '';
    """),
    (18, "Região panel — user-uploaded reference photo per região card", """
        -- A região card's thumbnail only ever showed the auto-generated
        -- painted-mask preview (or a flat color swatch before anything's
        -- painted) — no way to attach a real reference photo, unlike
        -- Mobs' portrait. Same loose-reference reasoning as mobs.
        -- image_path (migration 3): a plain column, no asset-library FK.
        ALTER TABLE painted_zones ADD COLUMN image_path TEXT DEFAULT '';
    """),
    (19, "Asset effect regions — painted grid per asset (emissive windows, aura, glitter, etc.)", """
        -- A flat JSON list of EFFECT_GRID_SIZE*EFFECT_GRID_SIZE cell keys
        -- (see src/engines/asset_effects.py) — every placed instance of
        -- that asset renders these as small local glow/particle effects
        -- (src/canvas/asset_effects_overlay.py), no new table needed since
        -- asset_settings already keys by the same asset_id.
        ALTER TABLE asset_settings ADD COLUMN effects_json TEXT DEFAULT '[]';
    """),
    (20, "Generic per-project UI state (key/value) — first use: remembers the last brush asset picked", """
        -- Small generic key/value store for "remember the last X" UI state
        -- that doesn't warrant its own dedicated table/column — starting
        -- with the Brush panel's last-picked asset (src/layouts/mediators/
        -- brush_mediator.py), reusable for future "last used ..." needs.
        CREATE TABLE IF NOT EXISTS ui_state (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    """),
    (21, "Mob categories — appearance customization (card/image border color, image asset)", """
        -- The category editor used to be a single inline name field with the
        -- icon hardcoded to '🐾' (see panel_category_mixin.py). Replacing it
        -- with a full edit panel (icon picker, card border color, an
        -- uploaded image, and a separate border color around that image)
        -- needs somewhere to persist those three new choices — empty string
        -- means "use the old hardcoded fallback" (category_badge_color /
        -- the emoji icon), so existing rows keep rendering exactly as before.
        ALTER TABLE mob_categories ADD COLUMN border_color TEXT DEFAULT '';
        ALTER TABLE mob_categories ADD COLUMN image_path TEXT DEFAULT '';
        ALTER TABLE mob_categories ADD COLUMN image_border_color TEXT DEFAULT '';
    """),
    (22, "Mob categories — preset sensible border colors for the seeded difficulty-tier folders", """
        -- Migration 21 added a real border_color column, but the 5
        -- folders migration 16 seeds (Normal/Raro/Elite/Épico/Boss) were
        -- left with the default '' — _SidebarRow reads border_color
        -- directly (not category_badge_color's hardcoded id->color
        -- fallback), so these rendered with no border color at all in the
        -- CATEGORIAS sidebar until now. Same color ladder
        -- category_badge_color already used for the mob card badge
        -- (gray/blue/purple/orange), plus a gold for Épico so it's not
        -- identical to Elite's purple. The `border_color = ''` guard
        -- avoids overwriting anything a user already picked by hand in
        -- the window between migration 21 and this one.
        UPDATE mob_categories SET border_color = '#9AA5B1' WHERE id = 'normal' AND border_color = '';
        UPDATE mob_categories SET border_color = '#4FC3F7' WHERE id = 'raro' AND border_color = '';
        UPDATE mob_categories SET border_color = '#AB47BC' WHERE id = 'elite' AND border_color = '';
        UPDATE mob_categories SET border_color = '#FFD54F' WHERE id = 'epico' AND border_color = '';
        UPDATE mob_categories SET border_color = '#FFA726' WHERE id = 'boss' AND border_color = '';
    """),
    (23, "Mob categories — replace migration 22's color guesses with the ones actually requested", """
        -- Migration 22 already ran (or may have already run) by the time
        -- these specific colors were picked, so this overwrites
        -- unconditionally for just these 4 ids rather than guarding on
        -- border_color = '' like migration 22 did — Raro is untouched,
        -- kept at migration 22's blue.
        UPDATE mob_categories SET border_color = '#A9C08C' WHERE id = 'normal';  -- verde musgo claro
        UPDATE mob_categories SET border_color = '#64B5F6' WHERE id = 'elite';   -- azul claro
        UPDATE mob_categories SET border_color = '#AB47BC' WHERE id = 'epico';   -- roxo
        UPDATE mob_categories SET border_color = '#FFA726' WHERE id = 'boss';    -- laranja
    """),
    (24, "Mob categories — customizable rarity-tag text color", """
        -- The rarity tag (MobCard's "Boss" pill, the Visão Geral category
        -- badge) had its text color hardcoded to white after border_color
        -- became user-editable — needed for contrast against whatever
        -- background color got picked, but not customizable itself. A 3rd
        -- color field alongside border_color/image_border_color; empty
        -- means "use white", same "no color chosen" convention as the
        -- other two (see category_badge_color/category_tag_text_color).
        ALTER TABLE mob_categories ADD COLUMN tag_text_color TEXT DEFAULT '';
    """),
    (25, "Mobs panel — height field, used to scale how much shadow a mob stamp casts", """
        ALTER TABLE mobs ADD COLUMN altura REAL DEFAULT 0;
    """),
    (26, "Brush tool — animated effect strokes (Névoa, Poeira, Chuva, ...), reusing painted_terrain's mask storage", """
        -- Painted with the Brush tool's "Effects" category, same mask
        -- mechanism as terrain/water (see painted_terrain, migration 10),
        -- just mask-only (no visible texture) — the animated look is
        -- painted per-frame by BrushEffectsOverlay instead (see
        -- src/engines/map/brush_effects.py). NULL for ordinary terrain/
        -- water rows; set to an ANIMATED_EFFECTS key (e.g. "Névoa") for an
        -- effect stroke.
        ALTER TABLE painted_terrain ADD COLUMN effect_key TEXT DEFAULT NULL;
    """),
    (27, "NPCs panel — full parity with Mobs: category tree, stamp assets, extended fields", """
        -- Mirrors migrations 3/4/5/8 for mobs, adapted to NPC semantics
        -- (no aggro/damage stats; instead state/reaction/attackable/flees/
        -- dies/respawns toggles matching the NPCs panel's Comportamento
        -- section). No FK from npcs.category into npc_categories, same
        -- loose-reference reasoning as mobs.category (migration 5).
        ALTER TABLE npcs ADD COLUMN title TEXT DEFAULT '';
        ALTER TABLE npcs ADD COLUMN npc_type TEXT DEFAULT 'Mercador';
        ALTER TABLE npcs ADD COLUMN category TEXT DEFAULT '';
        ALTER TABLE npcs ADD COLUMN subcategory TEXT DEFAULT '';
        ALTER TABLE npcs ADD COLUMN zone_id TEXT DEFAULT '';
        ALTER TABLE npcs ADD COLUMN level_recommended_min INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN level_recommended_max INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN health INTEGER DEFAULT 100;
        ALTER TABLE npcs ADD COLUMN mana INTEGER DEFAULT 50;
        ALTER TABLE npcs ADD COLUMN image_path TEXT DEFAULT '';
        ALTER TABLE npcs ADD COLUMN favorite INTEGER DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN status TEXT DEFAULT 'ativo';
        ALTER TABLE npcs ADD COLUMN position_z REAL DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN initial_state TEXT DEFAULT 'Neutro';
        ALTER TABLE npcs ADD COLUMN player_reaction TEXT DEFAULT 'Neutro';
        ALTER TABLE npcs ADD COLUMN can_be_attacked INTEGER DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN flees_when_attacked INTEGER DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN can_die INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN can_respawn INTEGER DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN respawn_time INTEGER DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN spawn_radius REAL DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN shadow_pct REAL DEFAULT 0;
        ALTER TABLE npcs ADD COLUMN visible_on_map INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN shows_on_minimap INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN shows_quest_icon INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN uses_animations INTEGER DEFAULT 1;
        ALTER TABLE npcs ADD COLUMN notes TEXT DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_npcs_category ON npcs(category);
        CREATE INDEX IF NOT EXISTS idx_npcs_zone ON npcs(zone_id);

        CREATE TABLE IF NOT EXISTS npc_categories (
            id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES npc_categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🧙',
            sort_order INTEGER DEFAULT 0,
            border_color TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            image_border_color TEXT DEFAULT '',
            tag_text_color TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_npc_categories_parent ON npc_categories(parent_id);

        CREATE TABLE IF NOT EXISTS npc_assets (
            id TEXT PRIMARY KEY,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            asset_type TEXT DEFAULT 'Modelo 3D',
            file_path TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            rarity TEXT DEFAULT 'common',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_npc_assets_npc ON npc_assets(npc_id);
    """),
]


def run_migrations(db: Database):
    """Apply all pending migrations."""
    # Ensure schema_version table exists
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.conn.commit()

    current = _get_current_version(db)
    pending = [m for m in MIGRATIONS if m[0] > current]

    for version, desc, sql in pending:
        logger.info("Aplicando migration %d: %s", version, desc)
        with db.transaction() as conn:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        logger.info("Migration %d aplicada com sucesso", version)


def _get_current_version(db: Database) -> int:
    row = db.fetchone("SELECT MAX(version) as v FROM schema_version")
    return row["v"] if row and row["v"] else 0
