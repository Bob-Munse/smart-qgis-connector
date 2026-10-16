# smart_connect_plugin.py
# This is the MAIN PLUGIN CLASS.
# It controls what happens when QGIS loads your plugin, and when the user clicks your menu items.

import os

from qgis.PyQt.QtGui import QIcon

try:
    # QGIS 3 (Qt5) keeps QAction in QtWidgets...
    from qgis.PyQt.QtWidgets import QAction
except ImportError:
    # ...QGIS 4 (Qt6) moved it to QtGui.
    from qgis.PyQt.QtGui import QAction

MENU_NAME = "SMART QGIS Connector"
ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "icon.png")   # SMART panther icon


class SmartQgisConnector:
    """
    This class IS the plugin, from QGIS's point of view.

    QGIS will call:
      - __init__()   when it first loads the plugin (at QGIS startup)
      - initGui()    when it is ready to add things to the QGIS interface
      - unload()     when the user disables or removes the plugin
    """

    def __init__(self, iface):
        """Called once when QGIS loads the plugin. `iface` gives access to the QGIS interface."""
        self.iface = iface
        self.dialog = None        # the main window, created the first time it's needed
        self.actions = []

    def initGui(self):
        """Create the toolbar button and the menu items."""
        parent = self.iface.mainWindow()
        icon = QIcon(ICON_PATH)

        # One toolbar button (with the plugin icon) opens the main window on the Import tab.
        self.main_action = QAction(icon, "SMART QGIS Connector", parent)
        self.main_action.setToolTip("SMART QGIS Connector — import SMART Connect data")
        self.main_action.triggered.connect(lambda: self.open_window(0))
        self.iface.addToolBarIcon(self.main_action)

        # Menu: Plugins > SMART Connect > Import Data / Connection Settings
        self.import_action = QAction(icon, "Import Data…", parent)
        self.import_action.triggered.connect(lambda: self.open_window(0))
        self.connect_action = QAction("Connection Settings…", parent)
        self.connect_action.triggered.connect(lambda: self.open_window(1))

        self.actions = [self.import_action, self.connect_action]
        for action in self.actions:
            self.iface.addPluginToMenu(MENU_NAME, action)

    def unload(self):
        """Remove everything added in initGui() — otherwise QGIS can crash."""
        for action in self.actions:
            self.iface.removePluginMenu(MENU_NAME, action)
        self.iface.removeToolBarIcon(self.main_action)
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def open_window(self, tab_index):
        """Show the main window (one shared window, so it remembers what you picked)."""
        # Imported here (not at the top) so QGIS starts quickly even if the
        # window code has a problem — the error only appears when you click.
        from .ui.main_dialog import SmartConnectDialog

        if self.dialog is None:
            self.dialog = SmartConnectDialog(self.iface.mainWindow(), self.iface)
        self.dialog.open_tab(tab_index)
