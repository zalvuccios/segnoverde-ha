"""Costanti per l'integrazione Segnoverde."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "segnoverde"

# Chiavi config entry (data + options)
CONF_CODICE_CLIENTE = "codice_cliente"
CONF_PASSWORD = "password"
CONF_DOWNLOAD_FOLDER = "download_folder"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_AUTO_DOWNLOAD_HISTORY = "auto_download_history"

DEFAULT_SCAN_INTERVAL = timedelta(hours=12)
MIN_SCAN_INTERVAL = timedelta(minutes=30)
DEFAULT_SCAN_INTERVAL_HOURS = 12
MIN_SCAN_INTERVAL_HOURS = 1

# Endpoint portale
BASE_URL = "https://segnoverde-webcli.serviceict.it/PortaleClienti"

# Stati pagamento
STATO_PAGATA = "PAGATA"
STATO_DA_PAGARE = "DA PAGARE"

# Stati login
LOGIN_OK = "OK"
LOGIN_PWDEXP = "PWDEXP"
LOGIN_REGNONATT = "REGNONATT"
LOGIN_NEWCDCLI = "NEWCDCLI"

PLATFORMS = ["sensor", "binary_sensor", "button"]

DEFAULT_AUTO_DOWNLOAD_HISTORY = True