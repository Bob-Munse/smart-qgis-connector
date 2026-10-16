# ui/main_dialog.py
# The plugin's MAIN WINDOW: a header with the connection status, a QGIS message
# bar, and two tabs (Import and Connection). Help and About sit at the bottom.

from qgis.gui import QgsMessageBar
from qgis.PyQt.QtCore import Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
)

from ..core import settings
from .common import HELP_URL, INFO, header_logo, plugin_icon, read_plugin_version, theme_icon
from .connection_panel import ConnectionPanel
from .import_panel import ImportPanel

IMPORT_TAB, CONNECTION_TAB = 0, 1

# Colour of the status dot only (text keeps the theme's colour, so dark mode works).
STATUS_COLOURS = {"ok": "#2e7d32", "error": "#c62828", "unknown": "#8a8a8a"}


class SmartConnectDialog(QDialog):
    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("SMART QGIS Connector")
        self.setWindowIcon(plugin_icon())
        self.setMinimumWidth(640)

        # ----- Header: icon, title, subtitle, connection status -----
        # The SMART logo sits on its own white tile, so it stays clear in light AND dark QGIS themes.
        icon_label = QLabel()
        icon_label.setPixmap(header_logo(52))
        icon_label.setStyleSheet("background: white; border: 1px solid #d0d0d0; border-radius: 6px; padding: 2px;")

        title = QLabel("SMART QGIS Connector")
        title_font = title.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 5)
        title_font.setBold(True)
        title.setFont(title_font)
        subtitle = QLabel("Bring patrol data from SMART Connect into QGIS")
        subtitle.setEnabled(False)   # muted text

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(title)
        titles.addWidget(subtitle)

        self.status_dot = QLabel("●")
        self.status_text = QLabel()
        self.server_text = QLabel()
        self.server_text.setEnabled(False)
        status_line = QHBoxLayout()
        status_line.setSpacing(6)
        status_line.addStretch(1)
        status_line.addWidget(self.status_dot)
        status_line.addWidget(self.status_text)
        status_box = QVBoxLayout()
        status_box.setSpacing(0)
        status_box.addLayout(status_line)
        status_box.addWidget(self.server_text, 0, Qt.AlignmentFlag.AlignRight)

        header = QHBoxLayout()
        header.addWidget(icon_label)
        header.addSpacing(6)
        header.addLayout(titles, 1)
        header.addLayout(status_box)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        # ----- QGIS-style message bar -----
        self.message_bar = QgsMessageBar()
        self.message_bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        # ----- Tabs -----
        self.connection_panel = ConnectionPanel(self.notify)
        self.import_panel = ImportPanel(
            self.notify, password_provider=self.connection_panel.current_password, iface=iface
        )
        self.tabs = QTabWidget()
        self.tabs.addTab(self.import_panel, theme_icon("mActionAddLayer.svg"), "Import")
        self.tabs.addTab(self.connection_panel, theme_icon("mIconConnect.svg"), "Connection")

        self.connection_panel.saved.connect(self._connection_saved)
        self.connection_panel.status_changed.connect(self.set_status)
        self.import_panel.status_changed.connect(self.set_status)

        # ----- Bottom buttons: Help + About on the left, Close on the right -----
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Help)
        buttons.button(QDialogButtonBox.StandardButton.Help).setIcon(theme_icon("mActionHelpContents.svg"))
        buttons.helpRequested.connect(lambda: QDesktopServices.openUrl(QUrl(HELP_URL)))
        about = QPushButton("About")
        buttons.addButton(about, QDialogButtonBox.ButtonRole.HelpRole)
        about.clicked.connect(self.show_about)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(separator)
        layout.addWidget(self.message_bar)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

        self._refresh_server_text()
        self.set_status("unknown", "Not checked yet")
        self._loaded_once = False

    # ------------------------------------------------------------------

    def notify(self, level, message, duration=None):
        """Show a message in the bar at the top. Successes fade after a few seconds.
        notify(None, "") just clears the bar."""
        self.message_bar.clearWidgets()
        if level is None:
            return
        if duration is None:
            duration = 6 if level in (INFO,) or "saved" in message.lower() or message.startswith("Added") else 0
        self.message_bar.pushMessage("", message, level, duration)

    def set_status(self, state, text):
        colour = STATUS_COLOURS.get(state, STATUS_COLOURS["unknown"])
        self.status_dot.setStyleSheet(f"color: {colour};")
        self.status_text.setText(text)

    def _refresh_server_text(self):
        saved = settings.load_settings()
        host = saved["server_url"].split("://")[-1] if saved["server_url"] else "No server set"
        self.server_text.setText(host)

    def _connection_saved(self):
        self._refresh_server_text()
        self.import_panel.reset_client()
        QTimer.singleShot(0, self.import_panel.load_queries)   # reload with the new login
        self.tabs.setCurrentIndex(IMPORT_TAB)

    def open_tab(self, index):
        """Show the window on the given tab (called from the plugin menu)."""
        if not self.connection_panel.is_configured():
            index = CONNECTION_TAB
            self.notify(INFO, "Welcome! Enter your SMART Connect details, click Test Connection, then Save.", 0)
        self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()
        self.activateWindow()
        if index == IMPORT_TAB and not self._loaded_once and self.connection_panel.is_configured():
            self._loaded_once = True
            QTimer.singleShot(0, self.import_panel.load_queries)

    def show_about(self):
        QMessageBox.about(
            self,
            "About SMART QGIS Connector",
            f"<b>SMART QGIS Connector</b> — version {read_plugin_version()}<br><br>"
            "Imports the results of saved SMART Connect queries into QGIS as map layers "
            "and tables.<br><br>"
            "SMART and the SMART logo belong to the SMART Partnership.<br><br>"
            f'<a href="{HELP_URL}">Documentation and source code</a>',
        )
