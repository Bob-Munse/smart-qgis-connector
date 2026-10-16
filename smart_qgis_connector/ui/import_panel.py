# ui/import_panel.py
# The IMPORT tab:
#   Source       — conservation area + a searchable list of your saved SMART queries
#   Time period  — which date to filter on, start/end dates, one-click presets
#   Output       — layer name and where the files are saved
# The download runs in the background (a QGIS task), so QGIS stays usable and
# the progress bar moves; Cancel stops it.

import os

from qgis.core import QgsApplication, QgsFeedback, QgsTask
from qgis.gui import QgsCollapsibleGroupBox
from qgis.PyQt.QtCore import QDate, QStringListModel, Qt, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QGuiApplication
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..api.smart_client import (
    SmartConnectClient,
    date_filters_for,
    describe_page,
    detect_payload_kind,
    geometry_kind_for,
    normalize_uuid,
)
from ..core import layers, settings
from .common import CRITICAL, INFO, KIND_LABELS, SUCCESS, WARNING, hint_label, kind_icon, theme_icon

DEFAULT_DAYS_BACK = 30

# Plain-language names for the date filters shown in the dropdown.
DATE_FILTER_LABELS = {
    "patrolstart": "Patrol start date",
    "patrolend": "Patrol end date",
    "waypointdate": "Waypoint (observation) date",
    "waypointlastmodified": "Waypoint last modified",
    "missionstartdate": "Mission start date",
    "missionenddate": "Mission end date",
    "missiontrackdate": "Mission track date",
    "assetdeploymentdate": "Asset deployment date",
    "RecordDate": "Record date",
}


class ImportPanel(QWidget):
    import_finished = pyqtSignal(bool)          # True if layers were added (used by tests)
    status_changed = pyqtSignal(str, str)       # state ("ok" / "error"), text for the header

    def __init__(self, notify, password_provider=None, iface=None, parent=None):
        """
        notify(level, message)  shows a message in the main window's message bar
        password_provider()     returns a password typed in the Connection tab, if any
        """
        super().__init__(parent)
        self.notify = notify
        self.password_provider = password_provider or (lambda: "")
        self.iface = iface

        self.client = None
        self.ca_uuid = ""
        self.all_queries = []      # every query from every conservation area
        self.queries = []          # only the chosen area's queries
        self.name_edited_by_user = False
        self.task = None
        self.feedback = None

        # ================= Source =================
        self.area_combo = QComboBox()
        self.area_combo.setToolTip("Only queries from this conservation area are listed.")
        self.area_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.area_combo.setMinimumContentsLength(24)

        self.query_combo = QComboBox()
        self.query_combo.setEditable(True)                       # type to search
        self.query_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.query_combo.lineEdit().setPlaceholderText("Type to search your queries…")
        self.query_combo.setToolTip("Your saved SMART Connect queries. Type a few letters to filter.")
        self._query_names = QStringListModel()
        completer = QCompleter(self._query_names, self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)       # match anywhere in the name
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.query_combo.setCompleter(completer)

        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(theme_icon("mActionRefresh.svg"))
        self.refresh_button.setToolTip("Reload the query list from the server.")
        self.refresh_button.clicked.connect(self.load_queries)

        query_row = QHBoxLayout()
        query_row.addWidget(self.query_combo, 1)
        query_row.addWidget(self.refresh_button)

        self.query_kind_label = hint_label("")

        self.paste_edit = QLineEdit()
        self.paste_edit.setClearButtonEnabled(True)
        self.paste_edit.setPlaceholderText("Optional: paste a query link or UUID instead")
        self.paste_edit.setToolTip("A query link or UUID copied from the SMART Connect website. Overrides the list.")

        source_form = QFormLayout()
        source_form.addRow("Conservation area:", self.area_combo)
        source_form.addRow("Query:", query_row)
        source_form.addRow("", self.query_kind_label)
        source_form.addRow("Or paste:", self.paste_edit)
        source_box = QGroupBox("Source")
        source_box.setLayout(source_form)

        # ================= Time period =================
        self.date_filter_combo = QComboBox()
        self.date_filter_combo.setToolTip("Which date field the start and end dates apply to.")

        today = QDate.currentDate()
        self.start_edit = QDateEdit(today.addDays(-DEFAULT_DAYS_BACK))
        self.end_edit = QDateEdit(today)
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)        # click to get a calendar
            edit.setDisplayFormat("yyyy-MM-dd")
        self.start_edit.setToolTip("First day included.")
        self.end_edit.setToolTip("Last day included (the whole day).")

        dates_row = QHBoxLayout()
        dates_row.addWidget(self.start_edit, 1)
        dates_row.addWidget(QLabel("to"))
        dates_row.addWidget(self.end_edit, 1)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(4)
        for label, handler in (
            ("Last 7 days", lambda: self._set_last_days(7)),
            ("Last 30 days", lambda: self._set_last_days(30)),
            ("This month", self._set_this_month),
            ("Last month", self._set_last_month),
            ("This year", self._set_this_year),
        ):
            button = QPushButton(label)
            button.setFlat(False)
            button.setAutoDefault(False)
            button.clicked.connect(handler)
            presets_row.addWidget(button)
        presets_row.addStretch(1)

        time_form = QFormLayout()
        time_form.addRow("Filter dates by:", self.date_filter_combo)
        time_form.addRow("Dates:", dates_row)
        time_form.addRow("Quick pick:", presets_row)
        time_box = QGroupBox("Time period")
        time_box.setLayout(time_form)

        # ================= Output =================
        self.layer_name_edit = QLineEdit()
        self.layer_name_edit.setToolTip("Name of the new layer(s) in the Layers panel.")
        self.layer_name_edit.textEdited.connect(self._user_typed_name)

        self.folder_label = hint_label("")
        self.folder_label.setWordWrap(False)   # one line; long paths are shortened with "…"
        self.open_folder_button = QToolButton()
        self.open_folder_button.setIcon(theme_icon("mIconFolder.svg"))
        self.open_folder_button.setToolTip("Open the folder where downloads are saved.")
        self.open_folder_button.clicked.connect(self._open_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(self.open_folder_button)

        output_form = QFormLayout()
        output_form.addRow("Layer name:", self.layer_name_edit)
        output_form.addRow("Saved in:", folder_row)
        output_box = QGroupBox("Output")
        output_box.setLayout(output_form)

        # ================= Progress + buttons =================
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)           # 0..0 = "busy" animation
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress.setVisible(False)
        self.progress_label = hint_label("")
        self.progress_label.setVisible(False)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_import)

        self.import_button = QPushButton(theme_icon("mActionAddLayer.svg"), "Import")
        self.import_button.setDefault(True)
        self.import_button.setToolTip("Download the query results and add them to the map.")
        self.import_button.clicked.connect(self.run_import)

        self.import_button.setMinimumWidth(110)
        actions = QHBoxLayout()
        actions.addWidget(self.progress_label, 1)
        actions.addStretch(0)                  # keeps the buttons on the right
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.import_button)

        # ================= Details (folded away) =================
        self.details_group = QgsCollapsibleGroupBox("Details")
        self.details_group.setCollapsed(True)
        self.details_box = QPlainTextEdit()
        self.details_box.setReadOnly(True)
        self.details_box.setMaximumHeight(160)
        self.details_box.setPlaceholderText("Each download attempt and any server message will appear here.")
        details_layout = QVBoxLayout()
        details_layout.addWidget(self.details_box)
        self.details_group.setLayout(details_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(source_box)
        layout.addWidget(time_box)
        layout.addWidget(output_box)
        layout.addWidget(self.progress)
        layout.addLayout(actions)
        layout.addWidget(self.details_group)
        layout.addStretch(1)

        # Keep the lists and layer name in step with the choices.
        self.area_combo.currentIndexChanged.connect(self._area_changed)
        self.query_combo.currentIndexChanged.connect(self._query_changed)
        self.query_combo.editTextChanged.connect(self._query_changed)   # typing in the search box
        self.paste_edit.textChanged.connect(self._query_changed)
        self.start_edit.dateChanged.connect(self._update_layer_name)
        self.end_edit.dateChanged.connect(self._update_layer_name)

        self._query_changed()
        self.refresh_folder_label()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def reset_client(self):
        """Forget the current login (called after Connection settings change)."""
        self.client = None

    def ensure_client(self):
        """Build a client from the saved connection settings. Returns False if not set up."""
        if self.client:
            return True
        saved = settings.load_settings()
        if not saved["server_url"] or not saved["username"]:
            self.notify(WARNING, "Set up your login first in the Connection tab.")
            return False
        password = settings.load_password(saved["authcfg"]) or self.password_provider()
        if not password:
            password, ok = QInputDialog.getText(
                self, "SMART Connect", f"Password for {saved['username']}:", QLineEdit.EchoMode.Password
            )
            if not ok or not password:
                self.notify(WARNING, "A password is needed to fetch data.")
                return False
        self.client = SmartConnectClient(saved["server_url"], saved["username"], password)
        self.ca_uuid = normalize_uuid(saved["ca_uuid"])
        return True

    # ------------------------------------------------------------------
    # Conservation areas and queries
    # ------------------------------------------------------------------

    def load_queries(self):
        """Fetch every saved query from the server, then fill the area dropdown."""
        if not self.ensure_client():
            return
        self.refresh_button.setEnabled(False)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            queries, error = self.client.list_queries()
        except Exception as exc:
            queries, error = [], f"Something went wrong: {exc}"
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.refresh_button.setEnabled(True)

        if error:
            self.notify(CRITICAL, error)
            self.status_changed.emit("error", "Not connected")
            return

        self.all_queries = queries
        self.status_changed.emit("ok", f"Connected as {self.client.username}")

        # Each conservation area once (alphabetical, because the query list is sorted).
        areas = []
        for q in queries:
            if q["ca_name"] not in areas:
                areas.append(q["ca_name"])

        # Which area to select: last choice, else the one matching the saved UUID, else the first.
        remembered = settings.load_import_area()
        by_uuid = next((q["ca_name"] for q in queries if self.ca_uuid and q["ca_uuid"] == self.ca_uuid), "")
        choice = remembered if remembered in areas else (by_uuid or (areas[0] if areas else ""))

        self.area_combo.blockSignals(True)   # don't react while we refill the list
        self.area_combo.clear()
        self.area_combo.addItems(areas)
        if choice:
            self.area_combo.setCurrentIndex(areas.index(choice))
        self.area_combo.blockSignals(False)
        self._area_changed()

        if not queries:
            self.notify(WARNING, "No saved queries were found for this account.")

    def _area_changed(self, *_):
        """Show only the queries that belong to the chosen conservation area."""
        area = self.area_combo.currentText()
        self.area_combo.setToolTip(area or "Only queries from this conservation area are listed.")
        if area:
            settings.save_import_area(area)    # remember for next time
        self.queries = [q for q in self.all_queries if q["ca_name"] == area]

        labels = []
        self.query_combo.blockSignals(True)
        self.query_combo.clear()
        for q in self.queries:
            # The area name is already in its own dropdown, so leave it out here.
            sub_folder = q["folder"][len(area):].lstrip("/") if q["folder"].startswith(area) else q["folder"]
            label = f"{sub_folder} / {q['name']}" if sub_folder else q["name"]
            kind = geometry_kind_for(q["type_key"])
            self.query_combo.addItem(kind_icon(kind), label)
            self.query_combo.setItemData(self.query_combo.count() - 1, KIND_LABELS.get(kind, ""), Qt.ItemDataRole.ToolTipRole)
            labels.append(label)
        self._query_names.setStringList(labels)
        self.query_combo.blockSignals(False)
        self._query_changed()

    def _current_query_index(self):
        """Index of the chosen query, or -1 if the typed text doesn't match one."""
        text = self.query_combo.currentText().strip()
        index = self.query_combo.currentIndex()
        if 0 <= index < len(self.queries) and self.query_combo.itemText(index) == text:
            return index
        return self.query_combo.findText(text, Qt.MatchFlag.MatchFixedString)

    def selected_query(self):
        """
        Return (uuid, type_key, name) for what the user chose.
        A pasted link/UUID wins over the list.
        """
        pasted = self.paste_edit.text().strip()
        if pasted:
            uuid = normalize_uuid(pasted)
            known = next((q for q in self.all_queries if q["uuid"] == uuid), None)
            if known:
                return uuid, known["type_key"], known["name"]
            return uuid, "", "SMART query"
        index = self._current_query_index()
        if 0 <= index < len(self.queries):
            q = self.queries[index]
            return q["uuid"], q["type_key"], q["name"]
        return "", "", ""

    def _query_changed(self, *_):
        _uuid, type_key, name = self.selected_query()
        current = self.date_filter_combo.currentData()
        self.date_filter_combo.clear()
        for key in date_filters_for(type_key):
            self.date_filter_combo.addItem(DATE_FILTER_LABELS.get(key, key), key)
        # Keep the user's previous choice if it's still allowed.
        if current:
            index = self.date_filter_combo.findData(current)
            if index >= 0:
                self.date_filter_combo.setCurrentIndex(index)
        self.query_kind_label.setText(KIND_LABELS.get(geometry_kind_for(type_key), "") if name else "")
        self._update_layer_name()

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def _set_range(self, start, end):
        self.start_edit.setDate(start)
        self.end_edit.setDate(end)

    def _set_last_days(self, days):
        today = QDate.currentDate()
        self._set_range(today.addDays(-(days - 1)), today)

    def _set_this_month(self):
        today = QDate.currentDate()
        self._set_range(QDate(today.year(), today.month(), 1), today)

    def _set_last_month(self):
        first_this = QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1)
        first_last = first_this.addMonths(-1)
        self._set_range(first_last, first_this.addDays(-1))

    def _set_this_year(self):
        today = QDate.currentDate()
        self._set_range(QDate(today.year(), 1, 1), today)

    # ------------------------------------------------------------------
    # Layer name and folder
    # ------------------------------------------------------------------

    def _user_typed_name(self, _text):
        self.name_edited_by_user = True

    def _update_layer_name(self, *_):
        if self.name_edited_by_user:
            return
        _uuid, _type, name = self.selected_query()
        start = self.start_edit.date().toString("yyyy-MM-dd")
        end = self.end_edit.date().toString("yyyy-MM-dd")
        self.layer_name_edit.setText(f"{name} {start} to {end}" if name else "")

    def refresh_folder_label(self):
        self._folder = layers.imports_folder(create=False)
        self.folder_label.setToolTip(self._folder)
        self._elide_folder()

    def _elide_folder(self):
        """Shorten a long folder path in the middle ("C:/Users/…/SMART Imports") to fit."""
        width = max(self.folder_label.width(), 200)
        metrics = self.folder_label.fontMetrics()
        self.folder_label.setText(metrics.elidedText(self._folder, Qt.TextElideMode.ElideMiddle, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_folder", None):
            self._elide_folder()

    def _open_folder(self):
        folder = layers.imports_folder(create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------------
    # Import (runs in the background)
    # ------------------------------------------------------------------

    def run_import(self):
        if self.task is not None:
            return                             # one import at a time
        if not self.ensure_client():
            return
        uuid, type_key, _name = self.selected_query()
        if not uuid:
            self.notify(WARNING, "Choose a query from the list, or paste a query link or UUID.")
            return
        if self.start_edit.date() > self.end_edit.date():
            self.notify(WARNING, "The start date is after the end date.")
            return

        date_filter = self.date_filter_combo.currentData()
        start = self.start_edit.date().toString("yyyy-MM-dd")
        end = self.end_edit.date().toString("yyyy-MM-dd")
        layer_name = self.layer_name_edit.text().strip() or "SMART query"
        self._details = [f"Query {uuid} (type: {type_key or 'unknown'}), {date_filter} {start} → {end}"]
        self._layer_name = layer_name

        self.feedback = QgsFeedback()
        client, feedback = self.client, self.feedback

        def work(task):
            # Runs in a background thread: only network work here, no widgets or layers.
            return client.download_query(uuid, date_filter, start, end, type_key, feedback)

        self.notify(None, "")                  # clear the previous message
        self.task = QgsTask.fromFunction(f"SMART Connect: importing {layer_name}", work, on_finished=self._import_done)
        self._set_busy(True)
        QgsApplication.taskManager().addTask(self.task)

    def cancel_import(self):
        if self.feedback is not None:
            self.feedback.cancel()
            self.progress_label.setText("Cancelling…")
            self.cancel_button.setEnabled(False)

    def _import_done(self, exception, result=None):
        """Runs back in the main thread when the background download finishes."""
        cancelled = self.feedback is not None and self.feedback.isCanceled()
        self.task, self.feedback = None, None
        self._set_busy(False)
        ok = False
        details = self._details

        if cancelled:
            self.notify(INFO, "Import cancelled.")
            details.append("Cancelled by user.")
        elif exception is not None or result is None:
            self.notify(CRITICAL, f"Something went wrong: {exception}")
            details.append(repr(exception))
        else:
            kind, body, error, log = result
            details += log
            if error:
                self.notify(CRITICAL, error)           # Details opens below with the full story
                # If the server sent a web page, keep it and show what it says.
                if detect_payload_kind(body) == "html":
                    details.append(describe_page(body))
                    details.append("Full page saved to: " + layers.save_failed_page(body, self._layer_name))
                self.details_group.setCollapsed(False)
                if "username or password" in error:
                    self.status_changed.emit("error", "Sign-in failed")
            else:
                try:
                    added, message, paths = layers.add_payload_as_layers(kind, body, self._layer_name)
                    details += ["Saved: " + p for p in paths]
                except Exception as exc:
                    added, message = 0, f"Couldn't add the data to the map: {exc}"
                ok = added > 0
                self.notify(SUCCESS if ok else WARNING, message)
                if ok and self.iface:
                    self.iface.messageBar().pushSuccess("SMART Connect", message)
                self.refresh_folder_label()

        self.details_box.setPlainText("\n".join(details))
        self.import_finished.emit(ok)

    def _set_busy(self, busy):
        self.progress.setVisible(busy)
        self.progress_label.setVisible(busy)
        self.progress_label.setText("Downloading from SMART Connect… large date ranges can take a few minutes.")
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.import_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
