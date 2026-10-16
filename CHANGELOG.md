# Changelog

All notable changes to SMART QGIS Connector are listed here.

## [0.6.0] - 2026-10-16
First release as **SMART QGIS Connector**.

### Added
- Import the results of saved SMART Connect queries as QGIS layers: patrol tracks (lines), observations (points), grid queries (polygons) and summary queries (tables).
- Conservation area picker and a searchable query list with layer-type icons.
- Date filters matched to each query type, plus quick picks (last 7/30 days, this/last month, this year).
- Background downloads with a progress bar and Cancel; up to 10 minutes for large date ranges.
- Automatic fallback from GeoJSON to zipped shapefile; every shapefile in a download becomes its own layer.
- Sign-in through SMART Connect's web login, with session handling and automatic re-login.
- Server error pages shown in a Details box and saved for troubleshooting.
- Connection tab with password stored encrypted in the QGIS Authentication Manager.

### Changed
- No server address is pre-filled; each organisation enters its own.