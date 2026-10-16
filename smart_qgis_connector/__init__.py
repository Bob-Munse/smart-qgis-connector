# __init__.py
# This is the ENTRY POINT of your plugin.
# QGIS looks for this file when it loads a plugin.
# It must contain a function called `classFactory` — that name is required by QGIS.

def classFactory(iface):
    """
    QGIS calls this function automatically when your plugin is loaded.

    `iface` is a QGIS object that gives your plugin access to everything in QGIS:
    - the map canvas (where layers are drawn)
    - the menu bar (to add your own menu items)
    - the toolbar (to add buttons)
    - the layer panel, and much more

    We pass `iface` into our main plugin class so it can use all of that.
    """
    from .plugin import SmartQgisConnector
    return SmartQgisConnector(iface)
