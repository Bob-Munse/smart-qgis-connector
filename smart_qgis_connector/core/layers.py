# core/layers.py
# This file turns what SMART Connect sends back into LAYERS ON THE QGIS MAP.
#
# Every download is first saved as a file in a "SMART Imports" folder:
#   - next to your QGIS project, if the project has been saved, or
#   - in your Documents folder otherwise.
# Because the layer points at a file on your computer, it stays in the project
# after you close QGIS and works offline in the field.

import json
import os
import re
import zipfile
from datetime import datetime

IMPORTS_FOLDER_NAME = "SMART Imports"
LAYER_GROUP_NAME = "SMART Connect"

# GeoJSON geometry type -> friendly suffix for the layer name
_GEOMETRY_FAMILIES = {
    "Point": "points", "MultiPoint": "points",
    "LineString": "lines", "MultiLineString": "lines",
    "Polygon": "polygons", "MultiPolygon": "polygons",
}


# ---------------------------------------------------------------------------
# Helpers (no QGIS needed)
# ---------------------------------------------------------------------------

def safe_filename(name):
    """'Coverage by team (2026-09-13 → 2026-10-13)' -> 'Coverage_by_team_2026-09-13_2026-10-13'"""
    name = re.sub(r"[^\w\-]+", "_", name or "smart_query", flags=re.UNICODE).strip("_")
    return name[:80] or "smart_query"


def split_geojson_by_geometry(data):
    """
    A SMART query can mix points, lines and polygons in one result.
    QGIS layers hold one geometry type each, so split the features into groups.

    Returns {"points": FeatureCollection, "lines": ..., "polygons": ..., "table": ...}
    containing only the groups that actually have features.
    """
    if isinstance(data, list):  # a bare list of features
        features = data
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = data.get("features") or []

    groups = {}
    for feature in features:
        geometry = feature.get("geometry") or {}
        family = _GEOMETRY_FAMILIES.get(geometry.get("type"), "table")
        groups.setdefault(family, []).append(feature)

    result = {}
    for family, feats in groups.items():
        collection = {"type": "FeatureCollection", "features": feats}
        if isinstance(data, dict) and data.get("crs"):
            collection["crs"] = data["crs"]
        result[family] = collection
    return result


# ---------------------------------------------------------------------------
# QGIS parts
# ---------------------------------------------------------------------------

def imports_folder(create=True):
    """Return the folder where downloads are saved (creating it unless create=False)."""
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import QStandardPaths

    base = QgsProject.instance().homePath()
    if not base:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) \
            or os.path.expanduser("~")
    folder = os.path.join(base, IMPORTS_FOLDER_NAME)
    if create:
        os.makedirs(folder, exist_ok=True)
    return folder


def _layer_group():
    """Find or create the 'SMART Connect' group at the top of the Layers panel."""
    from qgis.core import QgsProject

    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(LAYER_GROUP_NAME)
    if group is None:
        group = root.insertGroup(0, LAYER_GROUP_NAME)
    return group


def _add_to_map(layer):
    from qgis.core import QgsProject

    QgsProject.instance().addMapLayer(layer, False)  # False = we place it in our group ourselves
    _layer_group().insertLayer(0, layer)


def add_payload_as_layers(kind, body, layer_name):
    """
    Save the downloaded data to disk and add it to the map.
    Returns (number_of_layers_added, message, saved_paths).
    """
    from qgis.core import QgsRasterLayer, QgsVectorLayer
    from qgis.PyQt.QtCore import QUrl

    folder = imports_folder()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(folder, f"{safe_filename(layer_name)}_{stamp}")
    added, saved, feature_total = 0, [], 0

    if kind == "geojson":
        try:
            data = json.loads(body.decode("utf-8-sig"))  # "-sig" skips the invisible marker if present
        except (ValueError, UnicodeDecodeError):
            return 0, "The server's reply looked like GeoJSON but couldn't be read.", []
        groups = split_geojson_by_geometry(data)
        if not groups:
            return 0, "The query ran, but found no records in that date range.", []
        for family, collection in groups.items():
            suffix = "" if len(groups) == 1 else f" ({family})"
            path = f"{base}_{family}.geojson"
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(collection, handle)
            saved.append(path)
            layer = QgsVectorLayer(path, layer_name + suffix, "ogr")
            if layer.isValid():
                _add_to_map(layer)
                added += 1
                feature_total += layer.featureCount()

    elif kind == "csv":
        path = base + ".csv"
        with open(path, "wb") as handle:
            handle.write(body)
        saved.append(path)
        uri = QUrl.fromLocalFile(path).toString() + "?delimiter=,&detectTypes=yes&geomType=none"
        layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
        if layer.isValid():
            _add_to_map(layer)
            added += 1
            feature_total += layer.featureCount()

    elif kind == "zip":
        path = base + ".zip"
        with open(path, "wb") as handle:
            handle.write(body)
        saved.append(path)
        # A SMART shapefile download can hold several shapefiles (e.g. tracks AND waypoints).
        # Look inside the zip and add each .shp as its own layer.
        try:
            with zipfile.ZipFile(path) as archive:
                shp_names = [n for n in archive.namelist() if n.lower().endswith(".shp")]
        except zipfile.BadZipFile:
            shp_names = []
        # "/vsizip/" lets QGIS read straight from inside the zip; it wants forward slashes.
        zip_uri = "/vsizip/" + path.replace("\\", "/")
        for name in shp_names:
            short = os.path.splitext(os.path.basename(name))[0]
            label = layer_name if len(shp_names) == 1 else f"{layer_name} ({short})"
            layer = QgsVectorLayer(f"{zip_uri}/{name}", label, "ogr")
            if layer.isValid():
                _add_to_map(layer)
                added += 1
                feature_total += layer.featureCount()

    elif kind == "tiff":
        path = base + ".tif"
        with open(path, "wb") as handle:
            handle.write(body)
        saved.append(path)
        layer = QgsRasterLayer(path, layer_name)
        if layer.isValid():
            _add_to_map(layer)
            added += 1

    elif kind == "empty":
        return 0, "The query ran, but found no records in that date range.", []

    if not added:
        where = f" The raw download was kept at: {saved[0]}" if saved else ""
        return 0, "QGIS couldn't open the data the server sent." + where, saved

    layers_text = "1 layer" if added == 1 else f"{added} layers"
    records = ""
    if feature_total:
        records = " with 1 record" if feature_total == 1 else f" with {feature_total} records"
    return added, f"Added {layers_text}{records} to the map.", saved


def save_failed_page(body, layer_name):
    """
    Keep a copy of a web page the server sent instead of data, so it can be opened
    in a browser to read the server's full message. Returns the file path.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(imports_folder(), f"{safe_filename(layer_name)}_{stamp}_server_reply.html")
    with open(path, "wb") as handle:
        handle.write(body or b"")
    return path
