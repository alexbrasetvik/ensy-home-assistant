from unittest import mock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ensy_unofficial.client import FanMode, PresetMode

from .conftest import EnsyTestClient


@pytest.fixture(autouse=True)
async def with_mock_config_entry(mock_config_entry: MockConfigEntry) -> None: ...


class TestStateChanging:
    @pytest.mark.parametrize(
        "message_key, message_value, state_key, state_value",
        [
            ("temperature", "23", "sensor.target_temperature", "23"),
            ("status", "online", "binary_sensor.connectivity", "on"),
            ("status", "offline", "binary_sensor.connectivity", "off"),
            ("texauh", "17", "sensor.exhaust_air", "17"),
            ("textr", "20", "sensor.extract_air", "20"),
            ("tsupl", "21", "sensor.supply_air", "21"),
            ("tout", "18", "sensor.outside_air", "18"),
            ("he", "1", "binary_sensor.heater_element", "on"),
            ("overheating", "17", "sensor.heater_temperature", "17"),
        ],
    )
    async def test_set_state(
        self,
        hass: HomeAssistant,
        ensy_client: EnsyTestClient,
        message_key: str,
        message_value: str,
        state_key: str,
        state_value: str,
    ) -> None:
        await ensy_client.apply_state_messages({message_key: message_value})
        await hass.async_block_till_done()
        state = hass.states.get(state_key)
        assert state is not None and state.state == state_value

        # Apply some possibly other state:
        await ensy_client.apply_state_messages({"temperature": "23"})
        await hass.async_block_till_done()
        state = hass.states.get(state_key)
        # This state should still be the same:
        assert state is not None and state.state == state_value

    @pytest.mark.parametrize("fan_mode", (FanMode.LOW, FanMode.MEDIUM, FanMode.HIGH))
    async def test_set_boost_then_home(
        self,
        hass: HomeAssistant,
        ensy_client: EnsyTestClient,
        fan_mode: FanMode,
    ) -> None:
        await ensy_client.apply_state_messages({"party": "1"})
        await hass.async_block_till_done()
        state = hass.states.get("sensor.preset_mode")
        assert state is not None and state.state == "boost"

        # While in party mode, setting a custom fan mode should set the preset mode back to home
        with mock.patch(
            "tests.conftest.EnsyTestClient.set_preset_mode", return_value=None
        ) as p:
            ensy_client.set_fan_mode(fan_mode)
        p.assert_called_once_with(PresetMode.HOME)
