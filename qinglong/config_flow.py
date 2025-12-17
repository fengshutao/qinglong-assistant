"""Config flow for QingLong integration."""

from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import CONF_HOST, CONF_PORT
import aiohttp
import async_timeout
import json

from .const import (
    DOMAIN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SSL,
    DEFAULT_PORT,
    DEFAULT_SSL,
    API_AUTH,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="localhost"): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    
    protocol = "https" if data.get(CONF_SSL, DEFAULT_SSL) else "http"
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    client_id = data[CONF_CLIENT_ID]
    client_secret = data[CONF_CLIENT_SECRET]
    
    url = f"{protocol}://{host}:{port}{API_AUTH}"
    params = {
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    async with aiohttp.ClientSession() as session:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise CannotConnect(f"HTTP status: {response.status}")
                
                data_response = await response.json()
                if data_response.get("code") != 200:
                    raise InvalidAuth(data_response.get("message", "Authentication failed"))
                
                token = data_response.get("data", {}).get("token")
                if not token:
                    raise InvalidAuth("No token in response")
                
                # Store the validated data
                result = {
                    "title": f"青龙面板 ({host}:{port})",
                    "data": data.copy(),
                    "token": token
                }
                
                return result


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for QingLong."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Store the token in config entry data
                user_input["token"] = info["token"]
                
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""