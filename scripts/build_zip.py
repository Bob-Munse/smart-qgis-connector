"""
Build the ZIP file to install in QGIS or upload to plugins.qgis.org.

How to run it (from the repository's top folder):
    python scripts/build_zip.py

Or from the QGIS Python Console (Plugins > Python Console), if Python isn't
installed separately on your computer:
    import runpy; runpy.run_path(r"C:\\path\\to\\smart-qgis-connector\\scripts\\build_zip.py", run_name="__main__")

The finished ZIP appears in the dist/ folder, e.g. dist/smart_qgis_connector-0.6.0.zip
"""

import configparser
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent     # the repository's top folder
PLUGIN = ROOT / "smart_qgis_connector"                     # the plugin itself
DIST = ROOT / "dist"                                       # where the ZIP is written

# Things that must never go into the ZIP (the QGIS plugin site rejects them).
SKIP_FOLDERS = {"__pycache__"}
SKIP_ENDINGS = {".pyc", ".pyo"}

# Files from the top folder that should also travel inside the plugin.
EXTRA_FILES = ["LICENSE", "README.md"]


def plugin_version():
    """Read the version number from metadata.txt, so the ZIP name always matches it."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PLUGIN / "metadata.txt", encoding="utf-8")
    return parser["general"]["version"]


def should_skip(relative_path):
    parts = relative_path.parts
    if any(part in SKIP_FOLDERS or part.startswith(".") for part in parts):
        return True        # cache folders and hidden files/folders
    return relative_path.suffix in SKIP_ENDINGS


def main():
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / f"{PLUGIN.name}-{plugin_version()}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        # Everything inside the plugin folder, stored under one top-level folder,
        # e.g. smart_qgis_connector/plugin.py — this is the layout QGIS expects.
        for path in sorted(PLUGIN.rglob("*")):
            relative = path.relative_to(PLUGIN)
            if path.is_file() and not should_skip(relative):
                archive.write(path, f"{PLUGIN.name}/{relative.as_posix()}")

        for name in EXTRA_FILES:
            if (ROOT / name).is_file():
                archive.write(ROOT / name, f"{PLUGIN.name}/{name}")

    print(f"Built {zip_path}")


if __name__ == "__main__":
    main()