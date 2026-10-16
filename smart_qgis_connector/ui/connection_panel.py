# ui/connection_panel.py
# The CONNECTION tab: server address, login and conservation area.

from datetime import datetime

from qgis.gui import QgsPasswordLineEdit
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..api.smart_client import SmartConnectClient, normalize_server_url, normalize_uuid
from ..core import settings
from .common import CRITICAL, SUCCESS, WARNING, hint_label, theme_icon


class ConnectionPanel(QWidget):
    # Signals let the main window react without this tab knowing about it.
    saved = pyqtSignal()                     # settings were saved
    status_changed = pyqtSignal(str, str)    # state ("ok" / "error" / "unknown"), text

    def __init__(self, notify, parent=None):
        """notify(level, message) shows a message in the main window's message bar."""
        super().__init__(parent)
        self.notify = notify
        self.authcfg = ""

        # ----- Server and login -----
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(settings.EXAMPLE_SERVER_URL)
        self.server_edit.setToolTip("Address of your SMART Connect server, e.g. " + settings.EXAMPLE_SERVER_URL)

        self.username_edit = QLineEdit()
        self.username_edit.setToolTip("Your SMART Connect username.")

        self.password_edit = QgsPasswordLineEdit()   # has a built-in show/hide eye
        self.password_edit.setToolTip("Your SMART Connect password.")

        self.remember_check = QCheckBox("Remember password")
        self.remember_check.setToolTip(
            "Store the password encrypted in the QGIS Authentication Manager.\n"
            "QGIS may ask you to set a master password the first time."
        )

        server_form = QFormLayout()
        server_form.addRow("Server URL:", self.server_edit)
        server_form.addRow("Username:", self.username_edit)
        server_form.addRow("Password:", self.password_edit)
        server_form.addRow("", self.remember_check)
        server_box = QGroupBox("SMART Connect server")
        server_box.setLayout(server_form)

        # ----- Conservation area -----
        self.ca_uuid_edit = QLineEdit()
        self.ca_uuid_edit.setPlaceholderText("e.g. 1a2b3c4d-0000-1111-2222-333344445555")
        self.ca_uuid_edit.setToolTip("Used to pre-select your conservation area in the Import tab.")
        ca_form = QFormLayout()
        ca_form.addRow("Conservation area UUID:", self.ca_uuid_edit)
        ca_form.addRow("", hint_label(
            "Optional. Picks your area automatically in the Import tab; dashes are added for you."
        ))
        ca_box = QGroupBox("Conservation area")
        ca_box.setLayout(ca_form)

        # ----- Test + Save -----
        self.test_button = QPushButton(theme_icon("mIconConnect.svg"), "Test Connection")
        self.test_button.setToolTip("Check the server address, username and password.")
        self.test_button.clicked.connect(self.test_connection)

        self.last_test_label = QLabel()
        self.last_test_label.setEnabled(False)   # muted text

        self.save_button = QPushButton("Save")
        self.save_button.setDefault(True)
        self.save_button.setToolTip("Save these settings.")
        self.save_button.clicked.connect(self.save)

        actions = QHBoxLayout()
        actions.addWidget(self.test_button)
        actions.addWidget(self.last_test_label, 1)
        actions.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(server_box)
        layout.addWidget(ca_box)
        layout.addStretch(1)
        layout.addLayout(actions)

        self.load_saved_values()

    # ------------------------------------------------------------------

    def load_saved_values(self):
        saved = settings.load_settings()
        self.server_edit.setText(saved["server_url"])
        self.username_edit.setText(saved["username"])
        self.ca_uuid_edit.setText(saved["ca_uuid"])
        self.authcfg = saved["authcfg"]
        password = settings.load_password(self.authcfg)
        self.password_edit.setText(password)
        self.remember_check.setChecked(bool(password))
        last = settings.load_last_test()
        self.last_test_label.setText(f"Last tested: {last}" if last else "Not tested yet")

    def is_configured(self):
        saved = settings.load_settings()
        return bool(saved["server_url"] and saved["username"])

    def test_connection(self):
        client = SmartConnectClient(
            self.server_edit.text(), self.username_edit.text().strip(), self.password_edit.text()
        )
        self.test_button.setEnabled(False)
        self.last_test_label.setText("Testing…")
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            ok, message = client.test_connection()
        except Exception as exc:  # never let a network hiccup crash QGIS
            ok, message = False, f"Something went wrong: {exc}"
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.test_button.setEnabled(True)

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = "connected" if ok else "failed"
        settings.save_last_test(f"{stamp} — {result}")
        self.last_test_label.setText(f"Last tested: {stamp} — {result}")
        self.notify(SUCCESS if ok else CRITICAL, message)
        user = self.username_edit.text().strip()
        self.status_changed.emit("ok" if ok else "error", f"Connected as {user}" if ok else "Connection failed")

    def save(self):
        server_url = normalize_server_url(self.server_edit.text())
        username = self.username_edit.text().strip()
        if not server_url or not username:
            self.notify(WARNING, "Please enter the server URL and your username.")
            return
        # Accepts the UUID with or without dashes and stores the standard dashed form.
        ca_uuid = normalize_uuid(self.ca_uuid_edit.text()) or self.ca_uuid_edit.text().strip()

        authcfg = self.authcfg
        if self.remember_check.isChecked() and self.password_edit.text():
            authcfg = settings.store_password(username, self.password_edit.text(), self.authcfg)
            if not authcfg:
                self.notify(CRITICAL, "Couldn't store the password (the QGIS master password may not be set). "
                                      "Untick 'Remember password' to save without it.")
                return
        elif not self.remember_check.isChecked():
            settings.forget_password(self.authcfg)
            authcfg = ""

        settings.save_settings(server_url, username, ca_uuid, authcfg)
        self.authcfg = authcfg
        self.server_edit.setText(server_url)
        self.ca_uuid_edit.setText(ca_uuid)
        self.notify(SUCCESS, "Connection settings saved.")
        self.saved.emit()

    def current_password(self):
        """The password typed in this tab (used if it isn't stored)."""
        return self.password_edit.text()
