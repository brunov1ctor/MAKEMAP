"""FASE 27 — Plugin SDK."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any, Callable


# ─── Enums ───────────────────────────────────────────────────────────────────

class PluginState(Enum):
    DISCOVERED = auto()
    LOADED = auto()
    ACTIVE = auto()
    DISABLED = auto()
    ERROR = auto()


class HookType(Enum):
    ON_PROJECT_OPEN = auto()
    ON_PROJECT_SAVE = auto()
    ON_PROJECT_CLOSE = auto()
    ON_MAP_CHANGE = auto()
    ON_SELECTION_CHANGE = auto()
    ON_TOOL_CHANGE = auto()
    ON_ITEM_CREATE = auto()
    ON_ITEM_DELETE = auto()
    ON_ITEM_MODIFY = auto()
    ON_EXPORT = auto()
    ON_VALIDATE = auto()


class ExtensionType(Enum):
    TOOL = auto()
    PANEL = auto()
    EXPORTER = auto()
    GENERATOR = auto()
    BRUSH = auto()
    VALIDATOR = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class PluginMeta:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    dependencies: list[str] = field(default_factory=list)  # plugin ids
    min_app_version: str = "1.0.0"
    entry_point: str = ""  # module path


@dataclass
class PluginExtension:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    extension_type: ExtensionType = ExtensionType.TOOL
    name: str = ""
    config: dict = field(default_factory=dict)
    handler: Optional[Callable] = None


@dataclass
class Plugin:
    meta: PluginMeta = field(default_factory=PluginMeta)
    state: PluginState = PluginState.DISCOVERED
    extensions: list[PluginExtension] = field(default_factory=list)
    error: str = ""
    instance: Any = None  # the loaded plugin object


# ─── Plugin API (exposed to plugins) ────────────────────────────────────────

class PluginAPI:
    """Public API available to plugins for interacting with the editor."""

    def __init__(self, sdk: PluginSDK):
        self._sdk = sdk

    def register_tool(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.TOOL, name, handler, config)

    def register_panel(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.PANEL, name, handler, config)

    def register_exporter(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.EXPORTER, name, handler, config)

    def register_generator(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.GENERATOR, name, handler, config)

    def register_brush(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.BRUSH, name, handler, config)

    def register_validator(self, name: str, handler: Callable, config: dict = None) -> str:
        return self._sdk._register_extension(
            ExtensionType.VALIDATOR, name, handler, config)

    def on(self, hook: HookType, callback: Callable):
        self._sdk._add_hook(hook, callback)

    def get_selection(self) -> list[str]:
        return self._sdk._app_state.get("selection", [])

    def get_active_map(self) -> Optional[str]:
        return self._sdk._app_state.get("active_map")

    def get_active_tool(self) -> Optional[str]:
        return self._sdk._app_state.get("active_tool")

    def log(self, message: str):
        self._sdk._plugin_logs.append(message)


# ─── Plugin SDK ──────────────────────────────────────────────────────────────

class PluginSDK:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._extensions: dict[str, PluginExtension] = {}
        self._hooks: dict[HookType, list[Callable]] = {h: [] for h in HookType}
        self._app_state: dict[str, Any] = {}
        self._plugin_logs: list[str] = []
        self._active_plugin_id: Optional[str] = None
        self._api = PluginAPI(self)

    # ─── Discovery & Loading ─────────────────────────────────────────────

    def discover(self, meta: PluginMeta) -> Plugin:
        """Register a discovered plugin."""
        plugin = Plugin(meta=meta, state=PluginState.DISCOVERED)
        self._plugins[meta.id] = plugin
        return plugin

    def load_plugin(self, plugin_id: str) -> bool:
        """Load a plugin (simulate import of entry_point)."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False
        # Check dependencies
        for dep_id in plugin.meta.dependencies:
            dep = self._plugins.get(dep_id)
            if not dep or dep.state not in (PluginState.LOADED, PluginState.ACTIVE):
                plugin.state = PluginState.ERROR
                plugin.error = f"Missing dependency: {dep_id}"
                return False
        plugin.state = PluginState.LOADED
        return True

    def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a loaded plugin."""
        plugin = self._plugins.get(plugin_id)
        if not plugin or plugin.state != PluginState.LOADED:
            return False
        self._active_plugin_id = plugin_id
        plugin.state = PluginState.ACTIVE
        # Plugin would call api.register_* here via its activate() method
        if plugin.instance and hasattr(plugin.instance, "activate"):
            try:
                plugin.instance.activate(self._api)
            except Exception as ex:
                plugin.state = PluginState.ERROR
                plugin.error = str(ex)
                return False
        self._active_plugin_id = None
        return True

    def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin and remove its extensions."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False
        # Remove extensions
        to_remove = [eid for eid, ext in self._extensions.items()
                     if ext.plugin_id == plugin_id]
        for eid in to_remove:
            self._extensions.pop(eid)
        # Remove hooks
        for hook_list in self._hooks.values():
            hook_list[:] = [h for h in hook_list
                           if not getattr(h, "_plugin_id", None) == plugin_id]
        plugin.extensions.clear()
        plugin.state = PluginState.DISABLED
        if plugin.instance and hasattr(plugin.instance, "deactivate"):
            try:
                plugin.instance.deactivate()
            except Exception:
                pass
        return True

    def unload_plugin(self, plugin_id: str) -> bool:
        """Fully remove a plugin."""
        self.deactivate_plugin(plugin_id)
        return self._plugins.pop(plugin_id, None) is not None

    # ─── Extension Registration (internal) ───────────────────────────────

    def _register_extension(self, ext_type: ExtensionType, name: str,
                            handler: Callable, config: dict = None) -> str:
        plugin_id = self._active_plugin_id or ""
        ext = PluginExtension(
            plugin_id=plugin_id, extension_type=ext_type,
            name=name, handler=handler, config=config or {},
        )
        self._extensions[ext.id] = ext
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.extensions.append(ext)
        return ext.id

    def _add_hook(self, hook: HookType, callback: Callable):
        callback._plugin_id = self._active_plugin_id
        self._hooks[hook].append(callback)

    # ─── Hook Dispatch ───────────────────────────────────────────────────

    def emit(self, hook: HookType, **kwargs):
        """Dispatch a hook event to all registered listeners."""
        for callback in self._hooks.get(hook, []):
            try:
                callback(**kwargs)
            except Exception:
                pass  # sandboxed

    # ─── Queries ─────────────────────────────────────────────────────────

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def get_active_plugins(self) -> list[Plugin]:
        return [p for p in self._plugins.values() if p.state == PluginState.ACTIVE]

    def get_extensions(self, ext_type: ExtensionType = None) -> list[PluginExtension]:
        exts = list(self._extensions.values())
        if ext_type:
            exts = [e for e in exts if e.extension_type == ext_type]
        return exts

    def update_app_state(self, **kwargs):
        self._app_state.update(kwargs)

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def extension_count(self) -> int:
        return len(self._extensions)

    @property
    def logs(self) -> list[str]:
        return list(self._plugin_logs)
