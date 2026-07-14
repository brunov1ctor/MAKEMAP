"""FASE 23 — Map Export Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QImage, QPainter, QColor


# ─── Enums ───────────────────────────────────────────────────────────────────

class ExportFormat(Enum):
    PNG = auto()
    PNG_TRANSPARENT = auto()
    WEBP = auto()
    PDF = auto()
    TILES = auto()
    LAYER_PNG = auto()
    JSON = auto()
    CSV = auto()


class ExportScope(Enum):
    FULL_MAP = auto()
    SELECTION = auto()
    REGION = auto()
    LAYER = auto()
    VISIBLE = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class ExportOptions:
    format: ExportFormat = ExportFormat.PNG
    scope: ExportScope = ExportScope.FULL_MAP
    output_path: str = ""
    scale: float = 1.0              # 0.25 to 4.0
    quality: int = 90              # 1-100 for lossy formats
    background_color: QColor = field(default_factory=lambda: QColor(7, 17, 31))
    transparent: bool = False
    # Tiles
    tile_size: int = 256
    # Layer export
    layer_ids: list[str] = field(default_factory=list)
    # Region/selection
    region_rect: Optional[QRectF] = None
    # Metadata
    include_metadata: bool = False
    # Batch
    batch_items: list[str] = field(default_factory=list)  # map_ids for batch


@dataclass
class ExportResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    success: bool = True
    output_paths: list[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    file_size: int = 0
    error: str = ""


# ─── Map Export Engine ───────────────────────────────────────────────────────

class MapExportEngine:
    def __init__(self):
        self._results: list[ExportResult] = []

    def export(self, options: ExportOptions,
               render_callback=None) -> ExportResult:
        """
        Export map based on options.
        render_callback(painter, rect) is called to render content.
        """
        if options.format == ExportFormat.TILES:
            return self._export_tiles(options, render_callback)
        elif options.format == ExportFormat.LAYER_PNG:
            return self._export_layers(options, render_callback)
        elif options.format in (ExportFormat.JSON, ExportFormat.CSV):
            return self._export_data(options)
        else:
            return self._export_image(options, render_callback)

    def batch_export(self, options_list: list[ExportOptions],
                     render_callback=None) -> list[ExportResult]:
        results = []
        for opts in options_list:
            results.append(self.export(opts, render_callback))
        return results

    # ─── Image Export ────────────────────────────────────────────────────

    def _export_image(self, options: ExportOptions, render_callback) -> ExportResult:
        size = self._compute_size(options)
        fmt = QImage.Format_ARGB32 if options.transparent else QImage.Format_RGB32
        image = QImage(size, fmt)

        if options.transparent:
            image.fill(QColor(0, 0, 0, 0))
        else:
            image.fill(options.background_color)

        if render_callback:
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.scale(options.scale, options.scale)
            rect = options.region_rect or QRectF(0, 0, size.width() / options.scale,
                                                  size.height() / options.scale)
            render_callback(painter, rect)
            painter.end()

        path = self._resolve_path(options)
        ext = self._format_extension(options.format)
        quality = options.quality if options.format == ExportFormat.WEBP else -1
        saved = image.save(path, ext, quality)

        result = ExportResult(
            success=saved, output_paths=[path] if saved else [],
            width=size.width(), height=size.height(),
            error="" if saved else f"Failed to save: {path}",
        )
        self._results.append(result)
        return result

    # ─── Tiles Export ────────────────────────────────────────────────────

    def _export_tiles(self, options: ExportOptions, render_callback) -> ExportResult:
        size = self._compute_size(options)
        tile_size = options.tile_size
        cols = (size.width() + tile_size - 1) // tile_size
        rows = (size.height() + tile_size - 1) // tile_size
        output_dir = Path(options.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        for row in range(rows):
            for col in range(cols):
                tile = QImage(QSize(tile_size, tile_size), QImage.Format_ARGB32)
                tile.fill(QColor(0, 0, 0, 0) if options.transparent else options.background_color)

                if render_callback:
                    painter = QPainter(tile)
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.scale(options.scale, options.scale)
                    ox = col * tile_size / options.scale
                    oy = row * tile_size / options.scale
                    painter.translate(-ox, -oy)
                    rect = QRectF(ox, oy, tile_size / options.scale, tile_size / options.scale)
                    render_callback(painter, rect)
                    painter.end()

                tile_path = str(output_dir / f"tile_{row}_{col}.png")
                tile.save(tile_path, "PNG")
                paths.append(tile_path)

        result = ExportResult(
            success=True, output_paths=paths,
            width=size.width(), height=size.height(),
        )
        self._results.append(result)
        return result

    # ─── Layer Export ────────────────────────────────────────────────────

    def _export_layers(self, options: ExportOptions, render_callback) -> ExportResult:
        size = self._compute_size(options)
        output_dir = Path(options.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        layer_ids = options.layer_ids or ["layer_0"]
        for layer_id in layer_ids:
            image = QImage(size, QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))

            if render_callback:
                painter = QPainter(image)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.scale(options.scale, options.scale)
                rect = QRectF(0, 0, size.width() / options.scale, size.height() / options.scale)
                render_callback(painter, rect)
                painter.end()

            layer_path = str(output_dir / f"{layer_id}.png")
            image.save(layer_path, "PNG")
            paths.append(layer_path)

        result = ExportResult(
            success=True, output_paths=paths,
            width=size.width(), height=size.height(),
        )
        self._results.append(result)
        return result

    # ─── Data Export ─────────────────────────────────────────────────────

    def _export_data(self, options: ExportOptions) -> ExportResult:
        path = self._resolve_path(options)
        # Placeholder — actual data serialization depends on project model
        try:
            Path(path).write_text("{}" if options.format == ExportFormat.JSON else "", encoding="utf-8")
            result = ExportResult(success=True, output_paths=[path])
        except Exception as ex:
            result = ExportResult(success=False, error=str(ex))
        self._results.append(result)
        return result

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _compute_size(self, options: ExportOptions) -> QSize:
        if options.region_rect:
            w = int(options.region_rect.width() * options.scale)
            h = int(options.region_rect.height() * options.scale)
        else:
            w = int(2048 * options.scale)
            h = int(2048 * options.scale)
        return QSize(max(1, w), max(1, h))

    def _resolve_path(self, options: ExportOptions) -> str:
        if options.output_path:
            return options.output_path
        ext = self._format_extension(options.format)
        return f"export.{ext.lower()}"

    @staticmethod
    def _format_extension(fmt: ExportFormat) -> str:
        mapping = {
            ExportFormat.PNG: "PNG",
            ExportFormat.PNG_TRANSPARENT: "PNG",
            ExportFormat.WEBP: "WEBP",
            ExportFormat.PDF: "PDF",
            ExportFormat.TILES: "PNG",
            ExportFormat.LAYER_PNG: "PNG",
            ExportFormat.JSON: "json",
            ExportFormat.CSV: "csv",
        }
        return mapping.get(fmt, "PNG")

    # ─── Results ─────────────────────────────────────────────────────────

    def get_results(self) -> list[ExportResult]:
        return list(self._results)

    def clear_results(self):
        self._results.clear()

    @property
    def result_count(self) -> int:
        return len(self._results)
