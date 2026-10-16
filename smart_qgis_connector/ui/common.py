# ui/common.py
# Small helpers shared by the plugin's windows: icons, message levels and hint labels.

import os

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLabel

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ICON_PATH = os.path.join(PLUGIN_DIR, "icons", "icon.png")
SMART_LOGO_PATH = os.path.join(PLUGIN_DIR, "icons", "smart_logo.png")   # the SMART logo, shown in the header
HELP_URL = "https://github.com/Bob-Munse/smart-qgis-connector#readme"

# QGIS message levels (works on QGIS 3 and 4)
_LEVELS = getattr(Qgis, "MessageLevel", Qgis)
INFO, SUCCESS, WARNING, CRITICAL = _LEVELS.Info, _LEVELS.Success, _LEVELS.Warning, _LEVELS.Critical


def plugin_icon():
    return QIcon(PLUGIN_ICON_PATH)


def header_logo(size):
    """
    The picture for the top-left of the window: the SMART logo if its file is there,
    otherwise the plugin icon (so the header is never blank).
    """
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QPixmap

    logo = QPixmap(SMART_LOGO_PATH)
    if logo.isNull():
        return plugin_icon().pixmap(size, size)
    return logo.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def theme_icon(name):
    """One of QGIS's own icons, e.g. theme_icon('mActionRefresh.svg'). Matches light/dark themes."""
    return QgsApplication.getThemeIcon("/" + name)


# Small icon shown beside each query, by what it gives back.
_KIND_ICONS = {
    "point": "mIconPointLayer.svg",
    "line": "mIconLineLayer.svg",
    "polygon": "mIconPolygonLayer.svg",
    "table": "mIconTableLayer.svg",
}
KIND_LABELS = {
    "point": "Points (observations / waypoints)",
    "line": "Lines (patrol or mission tracks)",
    "polygon": "Polygons (grid cells)",
    "table": "Table (summary, no map features)",
    "unknown": "Unknown type",
}


def kind_icon(kind):
    name = _KIND_ICONS.get(kind)
    return theme_icon(name) if name else QIcon()


def hint_label(text):
    """A small, muted, word-wrapped label for short explanations under a field."""
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(font.pointSizeF() - 1, 7))
    label.setFont(font)
    label.setEnabled(False)   # disabled text colour = muted grey in every QGIS theme
    return label


def read_plugin_version():
    """The version number from metadata.txt (shown in the About box)."""
    import configparser

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
        return parser.get("general", "version", fallback="?")
    except configparser.Error:
        return "?"
