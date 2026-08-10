"""MAKEMAP Design System — Liquid Glass + Glassmorphism tokens."""


class Colors:
    BG_PRIMARY = "#07111F"
    BG_SECONDARY = "#0B1929"
    BG_TERTIARY = "#0F2133"
    BG_ELEVATED = "#132840"

    PANEL = "rgba(255, 255, 255, 0.08)"
    PANEL_HOVER = "rgba(255, 255, 255, 0.12)"
    PANEL_ACTIVE = "rgba(255, 255, 255, 0.15)"

    GLASS_BG = "rgba(11, 25, 41, 0.75)"
    GLASS_BG_STRONG = "rgba(11, 25, 41, 0.88)"
    GLASS_BORDER = "rgba(255, 255, 255, 0.12)"
    GLASS_HIGHLIGHT = "rgba(255, 255, 255, 0.06)"

    BORDER = "rgba(255, 255, 255, 0.18)"
    BORDER_HOVER = "rgba(255, 255, 255, 0.25)"
    BORDER_SUBTLE = "rgba(255, 255, 255, 0.08)"

    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "rgba(255, 255, 255, 0.7)"
    TEXT_MUTED = "rgba(255, 255, 255, 0.4)"
    TEXT_DISABLED = "rgba(255, 255, 255, 0.2)"

    ACCENT = "#4FC3F7"
    ACCENT_HOVER = "#81D4FA"
    ACCENT_GLOW = "rgba(79, 195, 247, 0.3)"
    ACCENT_DIM = "rgba(79, 195, 247, 0.15)"

    SUCCESS = "#66BB6A"
    WARNING = "#FFA726"
    ERROR = "#EF5350"
    INFO = "#42A5F5"
    PURPLE = "#AB47BC"
    ORANGE = "#FF7043"
    TEAL = "#26A69A"


class Metrics:
    BORDER_RADIUS = 20
    BORDER_RADIUS_SM = 12
    BORDER_RADIUS_XS = 8
    BORDER_RADIUS_XXS = 4
    BLUR = 28
    SHADOW = "0px 20px 60px rgba(0, 0, 0, 0.35)"
    SHADOW_SM = "0px 4px 12px rgba(0, 0, 0, 0.25)"
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 16
    SPACING_LG = 24
    SPACING_XL = 32
    TOP_BAR_HEIGHT = 72
    STATUS_BAR_HEIGHT = 30
    TOOLBAR_WIDTH = 36
    ICON_SM = 16
    ICON_MD = 20
    ICON_LG = 24


class Typography:
    FAMILY = "Segoe UI"
    SIZE_XXS = 9
    SIZE_XS = 10
    SIZE_SM = 12
    SIZE_MD = 14
    SIZE_LG = 18
    SIZE_XL = 24
    SIZE_XXL = 28
    WEIGHT_NORMAL = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_BOLD = 600
    WEIGHT_BLACK = 700


class Navigation:
    """Keyboard pan / navigation settings."""
    PAN_MIN_SPEED = 6.0       # px/frame at start
    PAN_MAX_SPEED = 36.0      # px/frame at full acceleration
    PAN_ACCEL_MS = 500        # ms to reach max speed
    PAN_FPS = 60              # timer tick rate
    ZOOM_STEP = 1.15          # scroll wheel zoom factor
    SCROLL_PAN_SPEED = 1.0    # multiplier for scroll-based pan

def combo_popup_qss(border: str = Colors.BORDER) -> str:
    """Shared QComboBox popup (QAbstractItemView) rule. Every panel styles
    its own QComboBox face differently (compact filter rows, inline layer
    combos, full-size form combos, ...) and that's legitimate — but each one
    used to hand-copy the *popup* rule too, and copies drifted apart (some
    missing a border, some using BORDER_SUBTLE vs BORDER, mismatched colors).
    Popups are separate top-level windows in Qt, so the popup's background
    must stay fully opaque (Colors.BG_ELEVATED, no alpha) — a translucent
    rgba() here renders as a garbled wrong color on Windows, since the popup
    window isn't marked translucent. Reuse this in every local
    _combo_style()/inline QComboBox stylesheet instead of retyping it."""
    return (
        f"QComboBox QAbstractItemView {{ background: {Colors.BG_ELEVATED}; "
        f"color: {Colors.TEXT_PRIMARY}; border: 1px solid {border}; "
        f"selection-background-color: {Colors.ACCENT_DIM}; }}"
    )


def menu_qss() -> str:
    """Shared QMenu popup style, used by every "..." overflow menu and
    dropdown menu across cards/panels. Reuse instead of hand-copying — every
    duplicate has drifted individually before."""
    return f"""
        QMenu {{
            background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER}; padding: 4px;
        }}
        QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
        QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
    """
