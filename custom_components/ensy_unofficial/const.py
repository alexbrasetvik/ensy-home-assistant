"""Constants for the ensy (unofficial) integration."""

from homeassistant.components.mqtt.const import CONF_TLS_INSECURE
from homeassistant.const import CONF_MAC, CONF_NAME

DOMAIN = "ensy_unofficial"
DEFAULT_NAME = "Ensy Ventilation Aggregate"
DEFAULT_CONF_TLS_INSECURE = False


__all__ = ["CONF_MAC", "CONF_NAME", "CONF_TLS_INSECURE", "DEFAULT_NAME", "DOMAIN"]
