# SMART QGIS Connector

Import the results of your saved **SMART Connect** queries straight into **QGIS**: patrol tracks, observations, grids and summary tables, without exporting and loading files by hand.

> Not an official SMART product. SMART and the SMART logo belong to the SMART Partnership.

## Features

- **Pick a query, pick dates, click Import.** Your saved SMART Connect queries are listed by conservation area, with a search box.
- **The right layer type, automatically:** patrol tracks become lines, observations become points, grid queries become polygons, and summary queries become attribute tables.
- **Quick date ranges:** last 7 or 30 days, this month, last month, this year.
- **Works with any SMART Connect server.** Enter your organisation's address once.
- **Keeps working offline.** Every download is saved locally in a `SMART Imports` folder.
- **Background downloads** with a progress bar and Cancel, so you can keep using QGIS.
- **Secure:** your password is stored encrypted in the QGIS Authentication Manager.

## Requirements

- QGIS 3.16 or newer (3.34 LTR recommended)
- A SMART Connect account with access to saved queries

## Installation

1. Download the latest `smart_qgis_connector-x.y.z.zip` from the [Releases](https://github.com/Bob-Munse/smart-qgis-connector/releases) page.
2. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**, choose the file and click **Install Plugin**.
3. The **SMART QGIS Connector** button appears on the Plugins toolbar.

## Getting started

### 1. Connect (once)

1. Click **SMART QGIS Connector** on the toolbar. The first time, the window opens on the **Connection** tab.
2. Enter your organisation's **Server URL** (e.g. `https://your-server.smartconservationtools.org`), your **Username** and **Password**.
3. Optionally enter your **Conservation Area UUID**, so your area is selected automatically.
4. Click **Test Connection**, then **Save**.

### 2. Import

1. On the **Import** tab, choose your **Conservation area** and a **Query**.
2. Choose **Filter dates by** and the date range, or click a quick pick.
3. Click **Import**. The results appear in a **SMART Connect** group in the Layers panel.

Map layers arrive in WGS 84 (EPSG:4326), and QGIS reprojects them on the fly to your project's coordinate system.

## Troubleshooting

Open **Details** at the bottom of the Import tab to see each download attempt and any message from the server.

| Message | What to do |
|---|---|
| Login failed: username or password is wrong | Check your details on the Connection tab |
| Could not reach the server | Check the Server URL and your internet connection |
| No records in that date range | Widen the dates, or try another **Filter dates by** option |
| The server sent a web page instead of data | Read the server's message in **Details**; the full page is saved in `SMART Imports` |
| Account isn't allowed to use the API | Ask your SMART Connect administrator to check your permissions |

Found a bug or have an idea? [Open an issue](https://github.com/Bob-Munse/smart-qgis-connector/issues).

## For developers

```
smart-qgis-connector/
├── smart_qgis_connector/   the plugin (this folder is what QGIS loads)
│   ├── plugin.py           toolbar button and menu
│   ├── api/                talks to the SMART Connect server
│   ├── core/               settings, and turning downloads into layers
│   ├── ui/                 the main window and its tabs
│   └── icons/
├── scripts/build_zip.py    builds the installable ZIP
├── CHANGELOG.md
└── LICENSE
```

**Run your working copy in QGIS (Windows):** link the plugin folder into QGIS's plugins folder, so QGIS runs the files you edit. Run this once in PowerShell:

```powershell
New-Item -ItemType Junction `
  -Path "$env:APPDATA\QGIS\QGIS4\profiles\default\python\plugins\smart_qgis_connector" `
  -Target "$HOME\Documents\GitHub\smart-qgis-connector\smart_qgis_connector"
```

Then enable the plugin in QGIS. The *Plugin Reloader* plugin reloads it after each change.

**Build the ZIP:** run `python scripts/build_zip.py`. The ZIP is written to `dist/`.

## Licence

GNU General Public License v3.0. See [LICENSE](LICENSE).

## Author

Chikuni Munsele Banda