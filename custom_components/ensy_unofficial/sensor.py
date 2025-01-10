from enum import Enum
from typing import cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ensy_unofficial.client import EnsyClient, EnsyState
from custom_components.ensy_unofficial.const import DOMAIN


class EnsyTemperatureSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, ensy_client: EnsyClient, name: str, state_key: str) -> None:
        self._ensy_client = ensy_client
        self._state_key = state_key

        self._attr_name = name
        self._attr_unique_id = f"sensor_{DOMAIN}_{ensy_client.mac_address}_{state_key}"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_native_value: int | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            via_device=(DOMAIN, f"climate_{DOMAIN}_{self._ensy_client.mac_address}"),
            name=self._attr_name,
            manufacturer="Ensy",
        )

    async def async_added_to_hass(self) -> None:
        self._ensy_client.on_state_updated.append(self._on_state_change)

    def _on_state_change(self, state: EnsyState) -> None:
        if (value := getattr(state, self._state_key)) is None:
            return
        assert isinstance(value, int)

        if value == self._attr_native_value:
            return

        self._attr_native_value = value
        self.schedule_update_ha_state()


class EnsyEnumSensor(SensorEntity):
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self, ensy_client: EnsyClient, name: str, state_key: str, options: list[str]
    ) -> None:
        self._ensy_client = ensy_client
        self._state_key = state_key
        self._attr_name = name
        self._attr_unique_id = f"sensor_{DOMAIN}_{ensy_client.mac_address}_{state_key}"
        self._attr_options = options
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            via_device=(DOMAIN, f"climate_{DOMAIN}_{self._ensy_client.mac_address}"),
            name=self._attr_name,
            manufacturer="Ensy",
        )

    async def async_added_to_hass(self) -> None:
        self._ensy_client.on_state_updated.append(self._on_state_change)

    def _on_state_change(self, state: EnsyState) -> None:
        if getattr(state, self._state_key) is None:
            return

        value = cast(Enum, getattr(state, self._state_key)).name.lower()
        if value == self._attr_native_value:
            return

        self._attr_native_value = value
        self.schedule_update_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    ensy_client = hass.data[DOMAIN][entry.entry_id]
    sensor_definitions = {
        "Target temperature": "temperature_target",
        "Extract air": "temperature_extract",
        "Exhaust air": "temperature_exhaust",
        "Supply air": "temperature_supply",
        "Outside air": "temperature_outside",
        "Heater temperature": "temperature_heater",
    }

    sensors = [
        EnsyTemperatureSensor(ensy_client, name, identifier)
        for name, identifier in sensor_definitions.items()
    ] + [
        EnsyEnumSensor(ensy_client, "Fan mode", "fan_mode", ["low", "medium", "high"]),
        EnsyEnumSensor(
            ensy_client, "Preset mode", "preset_mode", ["home", "away", "boost"]
        ),
    ]
    async_add_entities(sensors)
