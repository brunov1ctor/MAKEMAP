"""MAKEMAP global QSS stylesheet — Liquid Glass theme (transparent panels)."""

from src.styles.tokens import Colors, Metrics, Typography


def build_stylesheet() -> str:
    return f"""
    * {{
        font-family: "{Typography.FAMILY}";
        font-size: {Typography.SIZE_MD}px;
        color: {Colors.TEXT_PRIMARY};
    }}

    QWidget {{
        font-size: {Typography.SIZE_MD}px;
    }}

    QToolButton {{
        font-size: {Typography.SIZE_SM}px;
    }}

    QComboBox {{
        font-size: {Typography.SIZE_SM}px;
    }}

    QTabBar::tab {{
        font-size: {Typography.SIZE_SM}px;
    }}

    QTreeWidget {{
        font-size: {Typography.SIZE_SM}px;
    }}

    QHeaderView::section {{
        font-size: {Typography.SIZE_SM}px;
    }}

    QMainWindow {{
        background-color: transparent;
    }}

    /* --- Top Bar --- */
    QFrame#top_bar {{
        background-color: rgba(11, 18, 32, 180);
        border-bottom: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 0px;
    }}

    /* --- Status Bar --- */
    QFrame#status_bar {{
        background-color: rgba(11, 18, 32, 180);
        border-top: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 0px;
    }}

    /* --- Buttons --- */
    QPushButton {{
        background-color: rgba(28, 46, 74, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: {Metrics.BORDER_RADIUS_XS}px;
        padding: {Metrics.SPACING_SM}px {Metrics.SPACING_MD}px;
        color: {Colors.TEXT_PRIMARY};
    }}

    QPushButton:hover {{
        background-color: rgba(36, 58, 94, 0.65);
        border-color: rgba(255, 255, 255, 0.22);
    }}

    QPushButton:pressed {{
        background-color: rgba(44, 60, 90, 0.80);
        border-color: {Colors.ACCENT};
    }}

    /* --- Scrollbars --- */
    QScrollBar:vertical {{
        background: rgba(10, 16, 30, 0.30);
        width: 6px;
        border-radius: 3px;
        margin: 2px 0;
    }}

    QScrollBar::handle:vertical {{
        background: rgba(28, 46, 74, 0.60);
        border-radius: 3px;
        min-height: 30px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {Colors.ACCENT};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: rgba(10, 16, 30, 0.30);
        height: 6px;
        border-radius: 3px;
        margin: 0 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: rgba(28, 46, 74, 0.60);
        border-radius: 3px;
        min-width: 30px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {Colors.ACCENT};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    /* --- Labels --- */
    QLabel {{
        color: {Colors.TEXT_PRIMARY};
        background: transparent;
        border: none;
    }}

    QLabel#muted {{
        color: {Colors.TEXT_MUTED};
        font-size: {Typography.SIZE_SM}px;
    }}

    /* --- Line Edit --- */
    QLineEdit {{
        background-color: rgba(10, 16, 30, 0.70);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: {Metrics.BORDER_RADIUS_XS}px;
        padding: {Metrics.SPACING_SM}px;
        color: {Colors.TEXT_PRIMARY};
    }}

    QLineEdit:focus {{
        border: 2px solid {Colors.ACCENT};
        background-color: rgba(10, 16, 30, 0.80);
    }}

    /* --- Splitter --- */
    QSplitter::handle {{
        background: rgba(255, 255, 255, 0.08);
    }}

    QSplitter::handle:hover {{
        background: {Colors.ACCENT};
    }}

    QSplitter::handle:horizontal {{
        width: 1px;
    }}

    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* --- QGraphicsView (Canvas) --- */
    QGraphicsView {{
        background-color: transparent;
        border: none;
    }}

    /* --- ToolTip --- */
    QToolTip {{
        background-color: rgba(20, 32, 55, 0.92);
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 11px;
    }}

    /* --- TreeWidget --- */
    QTreeWidget {{
        background: transparent;
        border: none;
    }}

    /* --- TabWidget --- */
    QTabWidget::pane {{
        border: none;
        background: transparent;
    }}

    /* --- ScrollArea --- */
    QScrollArea {{
        background: transparent;
        border: none;
    }}

    /* --- ComboBox --- */
    QComboBox {{
        background-color: rgba(28, 46, 74, 0.55);
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        padding: 4px 10px;
    }}

    QComboBox:hover {{
        border-color: {Colors.ACCENT};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox QAbstractItemView {{
        background-color: rgba(20, 32, 55, 0.92);
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        selection-background-color: rgba(36, 58, 94, 0.80);
        selection-color: {Colors.ACCENT};
    }}
    """
