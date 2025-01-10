import logging
from typing import Any, Literal, cast

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_HOME,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ensy_unofficial.client import (
    EnsyClient,
    EnsyState,
    FanMode,
    PresetMode,
)
from custom_components.ensy_unofficial.const import CONF_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class EnsyClimate(ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
    )

    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT

    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_fan_mode: str | None = None

    _attr_preset_modes = [PRESET_HOME, PRESET_AWAY, PRESET_BOOST]
    _attr_preset_mode: Literal["home", "away", "boost"] | None = None

    _attr_min_temp = 15
    _attr_max_temp = 26
    _attr_target_temperature_step = 1

    _attr_should_poll = False

    def __init__(self, ensy_client: EnsyClient, name: str):
        self._ensy_client = ensy_client
        self._attr_unique_id = f"climate_{DOMAIN}_{ensy_client.mac_address}"
        self._attr_name = name

    async def async_added_to_hass(self) -> None:
        self._ensy_client.on_state_updated.append(self._on_state_change)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self._ensy_client.set_target_temperature(int(kwargs["temperature"]))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._ensy_client.set_fan_mode(FanMode[fan_mode.upper()])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in {"home", "away", "boost"}:
            raise ValueError(f"Invalid preset mode: [{preset_mode}]")

        self._ensy_client.set_preset_mode(cast(PresetMode, preset_mode))

    def _on_state_change(self, state: EnsyState) -> None:
        self._attr_target_temperature = state.temperature_target
        self._attr_current_temperature = state.temperature_extract

        if state.fan_mode:
            self._attr_fan_mode = state.fan_mode.name.lower()
        else:
            self._attr_fan_mode = None

        self._attr_preset_mode = cast(
            Literal["home", "away", "boost"],
            state.preset_mode and state.preset_mode.name.lower(),
        )

        self.schedule_update_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        assert self._attr_unique_id is not None
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name,
            manufacturer="Ensy",
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    ensy_client = hass.data[DOMAIN][entry.entry_id]
    ensy_climate = EnsyClimate(ensy_client, entry.data[CONF_NAME])
    async_add_entities([ensy_climate])
