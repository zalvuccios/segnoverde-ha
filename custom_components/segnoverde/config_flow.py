"""Config flow per Segnoverde."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SegnoverdeApiClient,
    SegnoverdeAuthError,
    SegnoverdeApiError,
    SegnoverdePwdExpiredError,
    SegnoverdeRegNotActiveError,
)
from .const import (
    BASE_URL,
    CONF_CODICE_CLIENTE,
    CONF_DOWNLOAD_FOLDER,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _schema_user(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CODICE_CLIENTE,
                default=defaults.get(CONF_CODICE_CLIENTE, ""),
            ): str,
            vol.Required(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
            ): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                description={
                    "suggested_value": defaults.get(CONF_SCAN_INTERVAL, 12)
                },
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
            vol.Optional(
                CONF_DOWNLOAD_FOLDER,
                description={
                    "suggested_value": defaults.get(
                        CONF_DOWNLOAD_FOLDER, "segnoverde_pdfs"
                    )
                },
            ): str,
        }
    )


async def _validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, str]:
    """Valida credenziali effettuando un login di prova."""
    session = async_get_clientsession(hass)
    client = SegnoverdeApiClient(
        data[CONF_CODICE_CLIENTE], data[CONF_PASSWORD], session
    )
    try:
        await client.async_login()
    except SegnoverdePwdExpiredError as err:
        raise SegnoverdeCredenzialiError("pwd_expired") from err
    except SegnoverdeRegNotActiveError as err:
        raise SegnoverdeCredenzialiError("reg_not_active") from err
    except SegnoverdeAuthError as err:
        raise SegnoverdeCredenzialiError("auth") from err
    except SegnoverdeApiError as err:
        raise SegnoverdeCredenzialiError("unknown") from err
    finally:
        await client.async_close()
    return {"title": f"Segnoverde {data[CONF_CODICE_CLIENTE]}"}


class SegnoverdeCredenzialiError(HomeAssistantError):
    """Errore di validazione credenziali."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow per Segnoverde."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # unique id per codice cliente
            await self.async_set_unique_id(user_input[CONF_CODICE_CLIENTE])
            self._abort_if_unique_id_configured()
            try:
                info = await _validate_input(self.hass, user_input)
            except SegnoverdeCredenzialiError as err:
                errors["base"] = err.code
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Errore inatteso durante validazione Segnoverde")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_CODICE_CLIENTE: user_input[CONF_CODICE_CLIENTE],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, 12),
                        CONF_DOWNLOAD_FOLDER: user_input.get(
                            CONF_DOWNLOAD_FOLDER, "segnoverde_pdfs"
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=_schema_user(), errors=errors
        )