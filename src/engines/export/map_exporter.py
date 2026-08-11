"""Map Exporter — renders the canvas scene to a PNG file, with an optional
area crop (map bounds vs. current viewport) and a decorative frame drawn on
top of the rendered image. Pure Qt logic, no panel/widget code, mirroring
src/engines/map/parallax.py's engine-without-widget shape."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen

from src.canvas.map_boundary import polygon_vertices_local
from src.canvas.lighting_overlay import GlobalLightingOverlay

LINE_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
}


def _content_bounding_rect(scene) -> QRectF:
    """Same idea as scene.itemsBoundingRect(), but skips whole-scene
    decorative overlays whose boundingRect() is deliberately the scene's
    fixed (huge, effectively-infinite) bounds for correct on-screen ambient
    painting — GlobalLightingOverlay (see its own boundingRect() docstring)
    — which would otherwise blow the auto-framed export/preview area up to
    the entire scene rect (QImage allocation then silently fails, since
    that's tens of millions of pixels on a side) any time a sky/light is
    configured."""
    rect = None
    for item in scene.items():
        if isinstance(item, GlobalLightingOverlay):
            continue
        r = item.sceneBoundingRect()
        rect = r if rect is None else rect.united(r)
    return rect if rect is not None else QRectF()


def _boundaries_union_path(engine) -> QPainterPath | None:
    """Real scene-space union of every visible terrain boundary — mirrors
    CanvasEngine._update_grid's own bounds-clip logic. A boundary can sit
    anywhere in the scene (positioned at the view center when created, or
    dragged since), so its shape/width/height alone — centered on the scene
    origin — isn't enough; the real per-item path is needed. Returns None if
    there's no active boundary (caller falls back to the origin-centered
    generic rect from engine._map_bounds)."""
    boundaries = [
        b for b in engine._brush_tool._all_boundaries
        if b is not None and b.visible and b._item is not None
    ]
    if not boundaries:
        return None
    union_path = QPainterPath()
    for b in boundaries:
        union_path = union_path.united(b._item.mapToScene(b._item.path()))
    return union_path


def _target_rect(engine, area: str) -> QRectF:
    """Scene-space rect to capture."""
    if area == "viewport":
        vp = engine.viewport
        return vp.mapToScene(vp.viewport().rect()).boundingRect()

    # Boundary real (posicionado onde o(s) terreno(s) realmente está(ão) na
    # cena) tem prioridade sobre o `_map_bounds` genérico abaixo.
    union_path = _boundaries_union_path(engine)
    if union_path is not None:
        return union_path.boundingRect()

    # Sem boundary ativo: enquadra todos os objetos da cena automaticamente
    # — preferido sobre o retângulo genérico de `_map_bounds` (que é só um
    # tamanho width/height centrado na origem da cena, sem relação com onde
    # o conteúdo real foi construído) para nunca exportar/pré-visualizar uma
    # área vazia quando o mapa "finito" não tem nenhum terreno delimitado
    # correspondendo a essa posição.
    scene_rect = _content_bounding_rect(engine.viewport.scene())
    if not scene_rect.isEmpty():
        # Adiciona margem de 5% para não cortar bordas de objetos
        margin_x = scene_rect.width() * 0.05
        margin_y = scene_rect.height() * 0.05
        return scene_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)

    bounds = engine._map_bounds
    if bounds:
        hw, hh = bounds["width"] / 2, bounds["height"] / 2
        return QRectF(-hw, -hh, bounds["width"], bounds["height"])
    return QRectF(0, 0, 1024, 1024)


def _clip_path(engine, area: str, rect: QRectF) -> QPainterPath | None:
    """Non-rectangular map-bounds shape to clip to, or None for a plain rect."""
    if area != "bounds":
        return None

    union_path = _boundaries_union_path(engine)
    if union_path is not None:
        return union_path

    bounds = engine._map_bounds
    if not bounds:
        return None

    vertices = polygon_vertices_local(bounds["shape"], bounds["width"], bounds["height"])
    if vertices is None:
        return None
    path = QPainterPath()
    path.moveTo(vertices[0])
    for pt in vertices[1:]:
        path.lineTo(pt)
    path.closeSubpath()
    return path


def _expand_grid_for_export(engine, rect: QRectF) -> bool:
    """Grid lines and the coordinate ruler are normally only rebuilt for a
    padded margin around whatever's currently on screen (see CanvasEngine.
    _update_grid — panning triggers a rebuild, the rest of the map is never
    drawn) — fine for live editing, but a "Limite do mapa" export/preview
    would then only show grid coverage wherever the user happened to have
    scrolled. Temporarily rebuild it across the exact export rect instead,
    so it (and the ruler) always fully covers what gets rendered here.
    Returns whether a rebuild happened, so the caller knows to restore the
    normal viewport-driven grid afterward."""
    grid = engine.grid
    if not (grid.visible or grid.show_measurements):
        return False
    zoom = engine.viewport.zoom_level
    clip_path = _boundaries_union_path(engine)
    grid.update(rect, zoom, clip_path, rect)
    return True


def _draw_solid_frame(painter: QPainter, image: QImage, options: dict):
    width = max(1, int(options.get("frame_width", 6)))
    color = QColor(options.get("frame_color", "#4FC3F7"))
    style = LINE_STYLES.get(options.get("frame_style", "solid"), Qt.PenStyle.SolidLine)
    radius = int(options.get("frame_radius", 0))

    inset = width / 2
    rect = QRectF(inset, inset, image.width() - width, image.height() - width)
    pen = QPen(color, width, style)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if options.get("frame_style") == "double":
        outer_pen = QPen(color, max(1, width / 3), Qt.PenStyle.SolidLine)
        painter.setPen(outer_pen)
        painter.drawRoundedRect(rect, radius, radius)
        gap = width
        inner_rect = rect.adjusted(gap, gap, -gap, -gap)
        painter.drawRoundedRect(inner_rect, max(0, radius - gap), max(0, radius - gap))
    else:
        painter.drawRoundedRect(rect, radius, radius)


def _draw_asset_frame(painter: QPainter, image: QImage, asset_path: str):
    frame_img = QImage(asset_path)
    if frame_img.isNull():
        return
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawImage(QRectF(0, 0, image.width(), image.height()), frame_img)


def _save_image(image: QImage, save_path: str, fmt: str) -> None:
    if fmt == "pdf":
        writer = QPdfWriter(save_path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setResolution(300)
        page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
        scale = min(page_rect.width() / image.width(), page_rect.height() / image.height())
        w, h = image.width() * scale, image.height() * scale
        x = page_rect.x() + (page_rect.width() - w) / 2
        y = page_rect.y() + (page_rect.height() - h) / 2
        painter = QPainter(writer)
        painter.drawImage(QRectF(x, y, w, h), image)
        painter.end()
        return

    if fmt == "jpg":
        # JPG has no alpha channel — flatten onto white first.
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(Qt.GlobalColor.white)
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        if not flat.save(save_path, "JPG"):
            raise IOError(f"Falha ao salvar imagem em {save_path}")
        return

    if not image.save(save_path, "PNG"):
        raise IOError(f"Falha ao salvar imagem em {save_path}")


def _render_export_image(engine, options: dict) -> QImage:
    area = options.get("area", "bounds")
    rect = _target_rect(engine, area)
    if rect.isEmpty():
        raise ValueError("Área de exportação vazia — nada para exportar.")

    image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    clip = _clip_path(engine, area, rect)
    local_clip = clip.translated(-rect.left(), -rect.top()) if clip is not None else None

    grid_expanded = _expand_grid_for_export(engine, rect)

    if local_clip is not None:
        painter.save()
        painter.setClipPath(local_clip)

    if not options.get("transparent_bg", False):
        engine.viewport.paint_export_background(painter, QRectF(image.rect()))

    engine.viewport.scene().render(painter, QRectF(image.rect()), rect)

    if local_clip is not None:
        painter.restore()

    if grid_expanded:
        engine._update_grid(force=True)

    frame_type = options.get("frame_type", "none")
    if frame_type == "solid":
        _draw_solid_frame(painter, image, options)
    elif frame_type == "asset" and options.get("frame_asset_path"):
        _draw_asset_frame(painter, image, options["frame_asset_path"])

    painter.end()
    return image


def export_map_image(engine, options: dict, save_path: str) -> None:
    """Renders `engine`'s scene to `save_path` using `options`:
    {area: "bounds"|"viewport", format: "png"|"jpg"|"pdf", transparent_bg: bool,
     frame_type: "none"|"solid"|"asset",
     frame_color, frame_width, frame_style, frame_radius, frame_asset_path}
    """
    image = _render_export_image(engine, options)
    _save_image(image, save_path, options.get("format", "png"))


def render_preview(engine, options: dict, max_width: int = 260, max_height: int = 120) -> QImage:
    """Same render as export_map_image, scaled down to fit within
    max_width/max_height — used by ExportPanel's live preview."""
    image = _render_export_image(engine, options)
    return image.scaled(
        max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
