"""Fixtures for testing."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from paho.mqtt.client import MQTTMessage
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ensy_unofficial.client import (
    EnsyClient,
)
from custom_components.ensy_unofficial.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class EnsyTestClient(EnsyClient):
    def __init__(self, hass: HomeAssistant, mac_address: str) -> None:
        super().__init__(hass, mac_address)
        self.published_messages: list[MQTTMessage] = []

    def get_unique_id_for_state_key(self, state_key: str) -> str:
        return f"sensor_{DOMAIN}_{self.mac_address}_{state_key}"

    def publish(
        self, topic: str, payload: str, qos: int = 1, retain: bool = True, **kwargs: Any
    ) -> None:
        message = MQTTMessage(topic=topic.encode("utf8"))
        message.payload = payload.encode("utf8")
        message.qos = qos
        message.retain = retain
        self.published_messages.append(message)

    async def apply_state_messages(self, states: dict[str, str]) -> None:
        for key, value in states.items():
            message = MQTTMessage(
                topic=f"{self._state_topic_prefix}{key}".encode("utf8")
            )
            message.payload = value.encode("utf8")
            self._on_message(self._mqtt_client, None, message)

        # The handlers get invoked from a thread, so they need to queue a task
        # So wait for those
        await self.hass.async_block_till_done()

    async def connect(self) -> None: ...

    async def disconnect(self) -> None:
        self._on_disconnect()
        await self.hass.async_block_till_done()


@pytest.fixture
async def ensy_client(hass: HomeAssistant) -> EnsyTestClient:
    client = EnsyTestClient(hass, "00:00:00:00:00:00")
    client.state.is_online = True
    return client


@pytest.fixture
async def mock_config_entry(
    hass: HomeAssistant, ensy_client: EnsyTestClient
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"mac": "00:00:00:00:00:00", "name": "Test", "tls_insecure": False},
    )
    hass.data[DOMAIN] = {entry.entry_id: ensy_client}
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    return entry
