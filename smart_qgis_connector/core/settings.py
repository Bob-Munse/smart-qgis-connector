# core/settings.py
# This file REMEMBERS the connection details between QGIS sessions.
#
# - Server URL, username and conservation area UUID are saved in QGIS's own
#   settings (QgsSettings), so they are filled in again next time you open the dialog.
# - The PASSWORD is never saved in plain text. If you tick "Remember password",
#   it goes into the QGIS Authentication Manager, which encrypts it with your
#   QGIS master password. We only keep the ID of that entry (the "authcfg").

from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings

# Every key we save starts with this prefix, so our settings stay grouped together.
SETTINGS_PREFIX = "smart_connect/"


# No server is filled in for new users — each organisation enters its own.
DEFAULT_SERVER_URL = ""
# Grey hint text shown inside the empty Server URL box. Never used to connect.
EXAMPLE_SERVER_URL = "https://your-server.smartconservationtools.org"

# Name shown for our entry in Settings > Options > Authentication.
AUTH_CONFIG_NAME = "SMART QGIS Connector"


def load_settings():
    """Return the saved connection details as a dictionary (password not included)."""
    s = QgsSettings()
    return {
        "server_url": s.value(SETTINGS_PREFIX + "server_url", DEFAULT_SERVER_URL),
        "username": s.value(SETTINGS_PREFIX + "username", ""),
        "ca_uuid": s.value(SETTINGS_PREFIX + "ca_uuid", ""),
        "authcfg": s.value(SETTINGS_PREFIX + "authcfg", ""),
    }


def save_settings(server_url, username, ca_uuid, authcfg=None):
    """Save the non-secret connection details. Pass authcfg="" to forget a stored password."""
    s = QgsSettings()
    s.setValue(SETTINGS_PREFIX + "server_url", server_url)
    s.setValue(SETTINGS_PREFIX + "username", username)
    s.setValue(SETTINGS_PREFIX + "ca_uuid", ca_uuid)
    if authcfg is not None:
        s.setValue(SETTINGS_PREFIX + "authcfg", authcfg)


def store_password(username, password, existing_authcfg=""):
    """
    Save username + password in the QGIS Authentication Manager.

    Returns the authcfg ID on success, or "" if QGIS refused
    (for example, the user cancelled the master-password prompt).
    """
    auth_manager = QgsApplication.authManager()

    config = QgsAuthMethodConfig()
    config.setName(AUTH_CONFIG_NAME)
    config.setMethod("Basic")
    config.setConfig("username", username)
    config.setConfig("password", password)

    # If we already have an entry, update it instead of creating a duplicate.
    if existing_authcfg and existing_authcfg in auth_manager.configIds():
        config.setId(existing_authcfg)
        ok = auth_manager.updateAuthenticationConfig(config)
        return existing_authcfg if ok else ""

    ok = auth_manager.storeAuthenticationConfig(config)
    # storeAuthenticationConfig returns a bool in some QGIS versions, and a tuple in others.
    if isinstance(ok, tuple):
        ok = ok[0]
    return config.id() if ok else ""


def load_password(authcfg):
    """Return the stored password for this authcfg ID, or "" if there isn't one."""
    if not authcfg:
        return ""
    auth_manager = QgsApplication.authManager()
    if authcfg not in auth_manager.configIds():
        return ""
    config = QgsAuthMethodConfig()
    # The last argument (True) asks QGIS to decrypt the secret fields.
    auth_manager.loadAuthenticationConfig(authcfg, config, True)
    return config.config("password", "")


def forget_password(authcfg):
    """Delete the stored password entry, if there is one."""
    if authcfg and authcfg in QgsApplication.authManager().configIds():
        QgsApplication.authManager().removeAuthenticationConfig(authcfg)


def load_import_area():
    """The conservation area last chosen in the Import Data window ("" if none yet)."""
    return QgsSettings().value(SETTINGS_PREFIX + "import_area", "")


def save_import_area(area_name):
    QgsSettings().setValue(SETTINGS_PREFIX + "import_area", area_name)


def load_last_test():
    """Text describing the last connection test, e.g. '2026-10-15 16:05 — connected'."""
    return QgsSettings().value(SETTINGS_PREFIX + "last_test", "")


def save_last_test(text):
    QgsSettings().setValue(SETTINGS_PREFIX + "last_test", text)
