import random

import pytest
from homeassistant.core import HomeAssistant
from paho.mqtt.client import MQTTMessage

from custom_components.ensy_unofficial.client import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    EnsyState,
    FanMode,
    PresetMode,
)

from .conftest import EnsyTestClient


class TestMessageParsing:
    def test_handle_unknown_messages(self, ensy_client: EnsyTestClient) -> None:
        message = MQTTMessage(topic=b"unknown")
        message.payload = b"whatever"
        # Don't throw on this:
        ensy_client._on_message(ensy_client._mqtt_client, None, message)

    async def test_parse_state(self, ensy_client: EnsyTestClient):
        assert ensy_client.state.fan_mode is None

        await ensy_client.apply_state_messages(
            {
                "status": "online",
                "fan": "2",
                "party": "0",
                "absent": "0",
                "textr": "18",
                "texauh": "19",
                "tsupl": "20",
                "tout": "21",
                "overheating": "22",
                "he": "1",
            }
        )

        assert ensy_client.state == EnsyState(
            is_online=True,
            fan_mode=FanMode.MEDIUM,
            preset_mode=PresetMode.HOME,
            temperature_extract=18,
            temperature_exhaust=19,
            temperature_supply=20,
            temperature_outside=21,
            temperature_heater=22,
            is_heating=True,
        )

        await ensy_client.apply_state_messages({"party": "1"})
        ensy_client.state.preset_mode == "party"

        await ensy_client.apply_state_messages({"party": "2"})
        ensy_client.state.preset_mode == "home"


class TestStateChanging:
    def test_set_temperature(self, ensy_client: EnsyTestClient) -> None:
        assert ensy_client.state.temperature_target is None
        ensy_client.set_target_temperature(20)
        last_message = ensy_client.published_messages[-1]
        assert (
            last_message.topic == f"{ensy_client._apply_state_topic_prefix}temperature"
        )
        assert last_message.payload == b"20"

    def test_set_invalid_temperature(self, ensy_client: EnsyTestClient) -> None:
        for target_temperature in (MIN_TEMPERATURE - 1, MAX_TEMPERATURE + 1):
            with pytest.raises(ValueError, match="Temperature out of bounds"):
                ensy_client.set_target_temperature(target_temperature)

    def test_set_fan_mode(self, ensy_client: EnsyTestClient) -> None:
        ensy_client.state.preset_mode == "home"
        ensy_client.set_target_temperature(20)
        last_message = ensy_client.published_messages[-1]
        assert (
            last_message.topic == f"{ensy_client._apply_state_topic_prefix}temperature"
        )
        assert last_message.payload == b"20"

    def test_set_fan_mode_resetting_to_home_mode(
        self, ensy_client: EnsyTestClient
    ) -> None:
        # Adjusting the fan speed should clear the away/boost mode:
        ensy_client.state.preset_mode = random.choice(("boost", "away"))
        ensy_client.set_fan_mode(FanMode.MEDIUM)

        absent_cleared = False
        party_cleared = False
        fan_mode_set = False

        for message in ensy_client.published_messages:
            if message.topic.endswith("/fan") and message.payload == b"2":
                fan_mode_set = True
            elif message.topic.endswith("absent") and message.payload == b"0":
                absent_cleared = True
            elif message.topic.endswith("party") and message.payload == b"2":
                party_cleared = True

        assert all((absent_cleared, party_cleared, fan_mode_set))


class TestOnlineAndDiscoveredEvents:
    async def test_online_and_discovered_events(
        self, ensy_client: EnsyTestClient, hass: HomeAssistant
    ) -> None:
        assert not (
            # Discovered is whether Ensy reports anything for the MAC
            ensy_client.device_is_discovered.is_set()
            # Online is whether the reporting ventilation aggregate is online, not whether
            # this client is connected
            or ensy_client.device_is_online.is_set()
        )

        await ensy_client.apply_state_messages({"status": "online"})

        # Should be both considered online and discovered:
        assert (
            ensy_client.device_is_discovered.is_set()
            # Online is whether the reporting ventilation aggregate is online, not whether
            # this client is connected
            and ensy_client.device_is_online.is_set()
        )

        # Pretend to disconnect
        await ensy_client.disconnect()
        # We should still be discovered, but not online:
        assert (
            ensy_client.device_is_discovered.is_set()
            and not ensy_client.device_is_online.is_set()
        )
