"""FASE 24 — Validation Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable

from PySide6.QtCore import QRectF


# ─── Enums ───────────────────────────────────────────────────────────────────

class Severity(Enum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class IssueType(Enum):
    BROKEN_ASSET = auto()
    BROKEN_REFERENCE = auto()
    OUTSIDE_MAP = auto()
    DUPLICATE_ID = auto()
    QUEST_LOOP = auto()
    MISSING_TEXTURE = auto()
    PERFORMANCE = auto()
    EMPTY_LAYER = auto()
    ORPHAN_ENTITY = auto()
    INVALID_CONNECTION = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: IssueType = IssueType.BROKEN_REFERENCE
    severity: Severity = Severity.WARNING
    message: str = ""
    entity_id: Optional[str] = None
    location: Optional[str] = None  # e.g. "Layer: Background", "Map: World"
    fix_available: bool = False
    ignored: bool = False


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)
    passed: bool = True
    total_checked: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity in (Severity.ERROR, Severity.CRITICAL) and not i.ignored)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING and not i.ignored)


# ─── Validation Rules ────────────────────────────────────────────────────────

@dataclass
class ValidationRule:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    issue_type: IssueType = IssueType.BROKEN_REFERENCE
    severity: Severity = Severity.WARNING
    enabled: bool = True
    check: Optional[Callable] = None  # callable(context) -> list[ValidationIssue]
    fix: Optional[Callable] = None    # callable(issue, context) -> bool


# ─── Validation Engine ───────────────────────────────────────────────────────

class ValidationEngine:
    def __init__(self):
        self._rules: list[ValidationRule] = []
        self._last_result: Optional[ValidationResult] = None
        self._ignored_ids: set[str] = set()
        self._auto_validate: bool = True
        self._init_rules()

    def _init_rules(self):
        """Register built-in validation rules."""
        self._rules = [
            ValidationRule(
                name="Broken Asset References",
                issue_type=IssueType.BROKEN_ASSET,
                severity=Severity.ERROR,
                check=self._check_broken_assets,
                fix=self._fix_remove_broken,
            ),
            ValidationRule(
                name="Broken Entity References",
                issue_type=IssueType.BROKEN_REFERENCE,
                severity=Severity.ERROR,
                check=self._check_broken_references,
                fix=self._fix_remove_broken,
            ),
            ValidationRule(
                name="Items Outside Map Bounds",
                issue_type=IssueType.OUTSIDE_MAP,
                severity=Severity.WARNING,
                check=self._check_outside_map,
                fix=self._fix_move_inside,
            ),
            ValidationRule(
                name="Duplicate IDs",
                issue_type=IssueType.DUPLICATE_ID,
                severity=Severity.CRITICAL,
                check=self._check_duplicate_ids,
            ),
            ValidationRule(
                name="Quest Chain Loops",
                issue_type=IssueType.QUEST_LOOP,
                severity=Severity.ERROR,
                check=self._check_quest_loops,
            ),
            ValidationRule(
                name="Missing Textures",
                issue_type=IssueType.MISSING_TEXTURE,
                severity=Severity.WARNING,
                check=self._check_missing_textures,
            ),
            ValidationRule(
                name="Performance Warnings",
                issue_type=IssueType.PERFORMANCE,
                severity=Severity.INFO,
                check=self._check_performance,
            ),
            ValidationRule(
                name="Empty Layers",
                issue_type=IssueType.EMPTY_LAYER,
                severity=Severity.INFO,
                check=self._check_empty_layers,
            ),
            ValidationRule(
                name="Orphan Entities",
                issue_type=IssueType.ORPHAN_ENTITY,
                severity=Severity.WARNING,
                check=self._check_orphan_entities,
            ),
            ValidationRule(
                name="Invalid Connections",
                issue_type=IssueType.INVALID_CONNECTION,
                severity=Severity.ERROR,
                check=self._check_invalid_connections,
            ),
        ]

    # ─── Validation ──────────────────────────────────────────────────────

    def validate(self, context: dict = None) -> ValidationResult:
        """Run all enabled rules against context."""
        ctx = context or {}
        result = ValidationResult()
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.check:
                issues = rule.check(ctx)
                for issue in issues:
                    issue.ignored = issue.id in self._ignored_ids
                result.issues.extend(issues)
                result.total_checked += 1
        result.passed = result.error_count == 0
        self._last_result = result
        return result

    def validate_on_save(self, context: dict = None) -> ValidationResult:
        """Auto-validation triggered on save."""
        if not self._auto_validate:
            return ValidationResult(passed=True)
        return self.validate(context)

    def quick_fix(self, issue_id: str, context: dict = None) -> bool:
        """Attempt to fix an issue automatically."""
        if not self._last_result:
            return False
        issue = next((i for i in self._last_result.issues if i.id == issue_id), None)
        if not issue or not issue.fix_available:
            return False
        rule = next((r for r in self._rules if r.issue_type == issue.issue_type), None)
        if rule and rule.fix:
            return rule.fix(issue, context or {})
        return False

    def fix_all(self, context: dict = None) -> int:
        """Fix all fixable issues. Returns count of fixed."""
        if not self._last_result:
            return 0
        fixed = 0
        for issue in self._last_result.issues:
            if issue.fix_available and not issue.ignored:
                if self.quick_fix(issue.id, context):
                    fixed += 1
        return fixed

    # ─── Issue Management ────────────────────────────────────────────────

    def ignore_issue(self, issue_id: str):
        self._ignored_ids.add(issue_id)

    def unignore_issue(self, issue_id: str):
        self._ignored_ids.discard(issue_id)

    def get_issues(self, severity: Severity = None,
                   issue_type: IssueType = None) -> list[ValidationIssue]:
        if not self._last_result:
            return []
        issues = self._last_result.issues
        if severity:
            issues = [i for i in issues if i.severity == severity]
        if issue_type:
            issues = [i for i in issues if i.issue_type == issue_type]
        return [i for i in issues if not i.ignored]

    @property
    def last_result(self) -> Optional[ValidationResult]:
        return self._last_result

    # ─── Rule Management ─────────────────────────────────────────────────

    def add_rule(self, rule: ValidationRule):
        self._rules.append(rule)

    def set_rule_enabled(self, name: str, enabled: bool):
        for rule in self._rules:
            if rule.name == name:
                rule.enabled = enabled
                return

    def set_auto_validate(self, enabled: bool):
        self._auto_validate = enabled

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ─── Built-in Checks ─────────────────────────────────────────────────

    def _check_broken_assets(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        assets = ctx.get("assets", {})
        items = ctx.get("items", [])
        for item in items:
            asset_id = item.get("asset_id")
            if asset_id and asset_id not in assets:
                issues.append(ValidationIssue(
                    issue_type=IssueType.BROKEN_ASSET, severity=Severity.ERROR,
                    message=f"Asset '{asset_id}' not found",
                    entity_id=item.get("id"), fix_available=True,
                ))
        return issues

    def _check_broken_references(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        entities = ctx.get("entities", {})
        connections = ctx.get("connections", [])
        for conn in connections:
            if conn.get("source_id") not in entities:
                issues.append(ValidationIssue(
                    issue_type=IssueType.BROKEN_REFERENCE, severity=Severity.ERROR,
                    message=f"Connection source '{conn.get('source_id')}' not found",
                    entity_id=conn.get("id"), fix_available=True,
                ))
            if conn.get("target_id") not in entities:
                issues.append(ValidationIssue(
                    issue_type=IssueType.BROKEN_REFERENCE, severity=Severity.ERROR,
                    message=f"Connection target '{conn.get('target_id')}' not found",
                    entity_id=conn.get("id"), fix_available=True,
                ))
        return issues

    def _check_outside_map(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        bounds = ctx.get("map_bounds")  # QRectF or dict
        items = ctx.get("items", [])
        if not bounds:
            return issues
        if isinstance(bounds, dict):
            bounds = QRectF(bounds["x"], bounds["y"], bounds["w"], bounds["h"])
        for item in items:
            x, y = item.get("x", 0), item.get("y", 0)
            if not bounds.contains(x, y):
                issues.append(ValidationIssue(
                    issue_type=IssueType.OUTSIDE_MAP, severity=Severity.WARNING,
                    message=f"Item '{item.get('name', item.get('id'))}' is outside map bounds",
                    entity_id=item.get("id"), fix_available=True,
                ))
        return issues

    def _check_duplicate_ids(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        seen = set()
        for item in ctx.get("items", []):
            item_id = item.get("id")
            if item_id in seen:
                issues.append(ValidationIssue(
                    issue_type=IssueType.DUPLICATE_ID, severity=Severity.CRITICAL,
                    message=f"Duplicate ID: {item_id}", entity_id=item_id,
                ))
            seen.add(item_id)
        return issues

    def _check_quest_loops(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        quests = ctx.get("quests", {})  # id -> {prerequisite_ids: [...]}
        def has_cycle(qid, visited, stack):
            visited.add(qid)
            stack.add(qid)
            for pre_id in quests.get(qid, {}).get("prerequisite_ids", []):
                if pre_id in stack:
                    return True
                if pre_id not in visited and has_cycle(pre_id, visited, stack):
                    return True
            stack.discard(qid)
            return False
        visited = set()
        for qid in quests:
            if qid not in visited:
                if has_cycle(qid, visited, set()):
                    issues.append(ValidationIssue(
                        issue_type=IssueType.QUEST_LOOP, severity=Severity.ERROR,
                        message=f"Quest chain cycle detected involving '{qid}'",
                        entity_id=qid,
                    ))
        return issues

    def _check_missing_textures(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        textures = ctx.get("textures", set())
        used = ctx.get("used_textures", [])
        for tex in used:
            if tex not in textures:
                issues.append(ValidationIssue(
                    issue_type=IssueType.MISSING_TEXTURE, severity=Severity.WARNING,
                    message=f"Texture '{tex}' not found", fix_available=True,
                ))
        return issues

    def _check_performance(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        item_count = ctx.get("item_count", 0)
        layer_count = ctx.get("layer_count", 0)
        if item_count > 10000:
            issues.append(ValidationIssue(
                issue_type=IssueType.PERFORMANCE, severity=Severity.WARNING,
                message=f"High item count ({item_count}). Consider using LOD or chunking.",
            ))
        if layer_count > 50:
            issues.append(ValidationIssue(
                issue_type=IssueType.PERFORMANCE, severity=Severity.INFO,
                message=f"Many layers ({layer_count}). Consider merging unused layers.",
            ))
        return issues

    def _check_empty_layers(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        layers = ctx.get("layers", {})  # id -> {name, item_count}
        for lid, info in layers.items():
            if info.get("item_count", 0) == 0:
                issues.append(ValidationIssue(
                    issue_type=IssueType.EMPTY_LAYER, severity=Severity.INFO,
                    message=f"Layer '{info.get('name', lid)}' is empty",
                    entity_id=lid,
                ))
        return issues

    def _check_orphan_entities(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        entities = ctx.get("entities", {})
        connections = ctx.get("connections", [])
        connected = set()
        for conn in connections:
            connected.add(conn.get("source_id"))
            connected.add(conn.get("target_id"))
        for eid, info in entities.items():
            if eid not in connected and info.get("type") not in ("resource", "spawn"):
                issues.append(ValidationIssue(
                    issue_type=IssueType.ORPHAN_ENTITY, severity=Severity.WARNING,
                    message=f"Entity '{info.get('name', eid)}' has no connections",
                    entity_id=eid,
                ))
        return issues

    def _check_invalid_connections(self, ctx: dict) -> list[ValidationIssue]:
        issues = []
        entities = ctx.get("entities", {})
        connections = ctx.get("connections", [])
        for conn in connections:
            src = conn.get("source_id")
            tgt = conn.get("target_id")
            if src == tgt:
                issues.append(ValidationIssue(
                    issue_type=IssueType.INVALID_CONNECTION, severity=Severity.ERROR,
                    message=f"Self-referencing connection on '{src}'",
                    entity_id=conn.get("id"), fix_available=True,
                ))
        return issues

    # ─── Built-in Fixes ──────────────────────────────────────────────────

    def _fix_remove_broken(self, issue: ValidationIssue, ctx: dict) -> bool:
        # Signal that the broken item/connection should be removed
        removals = ctx.setdefault("_removals", [])
        removals.append(issue.entity_id)
        return True

    def _fix_move_inside(self, issue: ValidationIssue, ctx: dict) -> bool:
        # Signal that the item should be clamped to map bounds
        moves = ctx.setdefault("_moves_inside", [])
        moves.append(issue.entity_id)
        return True
