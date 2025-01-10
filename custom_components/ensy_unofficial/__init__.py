import logging

from custom_components.ensy_unofficial.client import EnsyClient
from custom_components.ensy_unofficial.const import CONF_MAC, CONF_TLS_INSECURE, DOMAIN

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    config = entry.data
    mac_address = config[CONF_MAC]

    if (ensy_client := hass.data.setdefault(DOMAIN, {}).get(entry.entry_id)) is None:
        ensy_client = EnsyClient(
            hass, mac_address=mac_address, allow_insecure_tls=config[CONF_TLS_INSECURE]
        )
        hass.data[DOMAIN][entry.entry_id] = ensy_client

    # Let the entities wire before we connect, or state propagation can race the wiring:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ensy_client.connect()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    ensy_client = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if ensy_client:
        ensy_client.stop()
    return True
