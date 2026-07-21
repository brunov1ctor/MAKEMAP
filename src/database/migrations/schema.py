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
