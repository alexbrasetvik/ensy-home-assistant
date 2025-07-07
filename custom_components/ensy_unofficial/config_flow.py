import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info import dhcp

from custom_components.ensy_unofficial.client import EnsyClient
from custom_components.ensy_unofficial.const import (
    CONF_MAC,
    CONF_NAME,
    CONF_TLS_INSECURE,
    DEFAULT_CONF_TLS_INSECURE,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class EnsyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle DHCP discovery."""
        mac = format_mac(discovery_info.macaddress)
        await self.async_set_unique_id(mac)

        for entry in self._async_current_entries():
            if entry.data.get(CONF_MAC) == mac:
                return self.async_abort(reason="already_configured")  # type: ignore

        # Don't suggest it if we can't discover it:
        if not await EnsyClient.test_connectivity(self.hass, mac):
            return self.async_abort(reason="cannot_connect")  # type: ignore

        self.data[CONF_MAC] = mac

        return self.async_show_form(step_id="user")  # type: ignore

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            mac = user_input[CONF_MAC]

            for entry in self._async_current_entries():
                if entry.data.get(CONF_MAC) == mac:
                    return self.async_abort(reason="already_configured")  # type: ignore

            await self.async_set_unique_id(mac)

            if not await EnsyClient.test_connectivity(
                self.hass, mac, user_input.get(CONF_TLS_INSECURE, False)
            ):
                return self.async_abort(reason="cannot_connect")  # type: ignore

            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)  # type: ignore

        default_title = "Ensy Ventilation Aggregate"

        return self.async_show_form(  # type: ignore
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=default_title): str,
                    vol.Required(CONF_MAC, default=self.data.get(CONF_MAC)): str,
                    vol.Required(
                        CONF_TLS_INSECURE,
                        default=self.data.get(
                            CONF_TLS_INSECURE, DEFAULT_CONF_TLS_INSECURE
                        ),
                    ): bool,
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        reconfigure_entry = self._get_reconfigure_entry()
        data = reconfigure_entry.data

        if user_input is not None:
            mac = user_input[CONF_MAC]
            if mac != data[CONF_MAC]:
                if not await EnsyClient.test_connectivity(
                    self.hass, mac, user_input.get(CONF_TLS_INSECURE, False)
                ):
                    return self.async_abort(reason="cannot_connect")  # type: ignore

            return self.async_update_reload_and_abort(
                reconfigure_entry,
                title=user_input[CONF_NAME],
                data=user_input,
                reload_even_if_entry_is_unchanged=False,
            )  # type: ignore

        return self.async_show_form(  # type: ignore
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=data.get(CONF_NAME, DEFAULT_NAME),
                    ): str,
                    vol.Required(CONF_MAC, default=data.get(CONF_MAC)): str,
                    vol.Required(
                        CONF_TLS_INSECURE,
                        default=data.get(CONF_TLS_INSECURE, DEFAULT_CONF_TLS_INSECURE),
                        description="Allow insecure TLS? Ensy keeps not renewing their certificate in time, so this might be needed",
                    ): bool,
                }
            ),
        )
