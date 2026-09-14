"""Config flow: three fields, validated by actually talking to the station.

Everything the station exposes is local, so there is no account to sign into — but Tuya's LAN
protocol is encrypted with a per-device local key that only the vendor app knows. See the README
for how to read it out of the Osite app; there's nothing to reverse engineer, the Tuya SDK logs it.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_MODEL, DEFAULT_MODEL, DOMAIN
from .tuya_client import OstationClient, OstationError

_LOGGER = logging.getLogger(__name__)

# Tuya ids and keys are fixed-width; catching a mistyped key here beats a connection that fails
# with an opaque decrypt error much later.
_DEVICE_ID_LEN = 22
_LOCAL_KEY_LEN = 16

_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_DEVICE_ID): str,
    vol.Required(CONF_LOCAL_KEY): str,
    vol.Optional(CONF_NAME, default=DEFAULT_MODEL): str,
})


class OlightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one Ostation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device_id = user_input[CONF_DEVICE_ID].strip()
            local_key = user_input[CONF_LOCAL_KEY].strip()

            if len(device_id) != _DEVICE_ID_LEN:
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            if len(local_key) != _LOCAL_KEY_LEN:
                errors[CONF_LOCAL_KEY] = "invalid_local_key"

            if not errors:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                client = OstationClient(device_id, host, local_key)
                try:
                    await self.hass.async_add_executor_job(client.status)
                except OstationError as err:
                    _LOGGER.debug("Ostation validation failed: %s", err)
                    errors["base"] = "cannot_connect"
                finally:
                    await self.hass.async_add_executor_job(client.close)

            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_MODEL,
                    data={
                        CONF_HOST: host,
                        CONF_DEVICE_ID: device_id,
                        CONF_LOCAL_KEY: local_key,
                        CONF_MODEL: DEFAULT_MODEL,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_SCHEMA, user_input or {}),
            errors=errors,
        )
