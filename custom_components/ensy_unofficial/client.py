from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum, auto
from typing import Any

from homeassistant.components.mqtt.async_client import AsyncMQTTClient
from homeassistant.core import HomeAssistant
from paho.mqtt.client import Client as MQTTClient
from paho.mqtt.client import MQTTMessage

_LOGGER = logging.getLogger(__name__)

API_HOST = "app.ensy.no"
API_PORT = 8083

MIN_TEMPERATURE = 15
MAX_TEMPERATURE = 26


class FanMode(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class PresetMode(StrEnum):
    HOME = auto()
    AWAY = auto()
    BOOST = auto()


@dataclass
class EnsyState:
    is_heating: bool | None = None
    is_online: bool = False

    fan_mode: FanMode | None = None
    preset_mode: PresetMode | None = None

    temperature_exhaust: int | None = None
    temperature_extract: int | None = None
    temperature_heater: int | None = None
    temperature_outside: int | None = None
    temperature_supply: int | None = None
    temperature_target: int | None = None


class EnsyClient:
    """Wrapper for an MQTT client that knows how to use Ensy's websockets-based MQTT endpoint,
    with configurable security, since Ensy has room for improvement wrt. maintaining their
    certificates.

    Integration author is neither a Home Assistant nor MQTT expert. I looked at whether I could
    just have the Mosquitto broker bridge the upstream MQTT endpoint, but that doesn't seem
    possible to do when upstream is websockets based. Thus this little wrapper.
    """

    def __init__(
        self, hass: HomeAssistant, mac_address: str, allow_insecure_tls: bool = False
    ) -> None:
        self.on_state_updated: list[Callable[[EnsyState], None]] = []
        self.allow_insecure_tls = allow_insecure_tls
        self.hass = hass
        # The MAC address can't contain ":"s.
        self.mac_address = mac_address.replace(":", "").lower()
        self.device_is_online = asyncio.Event()
        self.device_is_discovered = asyncio.Event()
        self._state_topic_prefix = f"units/{self.mac_address}/unit/"
        self._apply_state_topic_prefix = f"units/{self.mac_address}/app/"

        # Despite the name, this thing is still threaded.
        # The infrastructure that makes it more ergonomic to use with asyncio is very tied to the
        # built-in MQTT functionality, which isn't suitable to connect to an external websockets based
        # endpoint.
        self._mqtt_client = AsyncMQTTClient(
            transport="websockets",
            # Reconnecting on failure is the default, but be explicit.
            # It's important to be nice to upstream and not retry too hard.
            # The paho client seems to do exponential 2**x backoff from 1 to 120 seconds.
            # Unjittered backoff, but overall not very aggressive anyway.
            reconnect_on_failure=True,
        )
        # AsyncMQTTClient gets rid of locks that shouldn't be necessary since asyncio is inherently
        # single-threaded.
        self._mqtt_client.setup()

        self._mqtt_client.ws_set_options(path="/mqtt")

        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.on_disconnect = self._on_disconnect
        self._mqtt_client.on_connect_fail = self._on_connect_fail

        self.state = EnsyState()

    async def _configure_insecure_tls(self) -> None:
        # Ensy is not doing a good job at timely refreshing their TLS certs.
        # Preferably, we could verify the hostname and disregard just the expiry, but that
        # turned out to be too much of a hassle.
        # Ensy's setup is fairly insecure anyway, the MAC is the only authenticator, and
        # there's only 16 million possible ones for their vendor's MAC range.
        # The device itself connects even though the TLS cert is expired.

        def _set_tls_context() -> None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            context.load_default_certs()
            self._mqtt_client.tls_set_context(context)

        # Run blocking call in the background:
        await self.hass.async_add_executor_job(_set_tls_context)
        _LOGGER.debug("Configured TLS mode insecure")

    async def _configure_secure_tls(self) -> None:
        await self.hass.async_add_executor_job(self._mqtt_client.tls_set)

    async def configure_tls(self) -> None:
        if self.allow_insecure_tls:
            await self._configure_insecure_tls()
        else:
            await self._configure_secure_tls()

    async def connect(self) -> None:
        await self.configure_tls()

        # These spin up a background thread. Author is unlikely to ever own more than a single
        # ventilation unit per install, so we don't attempt to share clients. PRs welcome.
        self._mqtt_client.connect_async(API_HOST, API_PORT)
        self._mqtt_client.loop_start()
        _LOGGER.debug("Started Ensy client")

    def stop(self) -> None:
        self.hass.async_add_executor_job(self._mqtt_client.loop_stop)
        _LOGGER.debug("Stopped Ensy client")

    def subscribe(self, topic: str, **kwargs: Any) -> None:
        self._mqtt_client.subscribe(topic, **kwargs)

    def publish(
        self, topic: str, payload: str, qos: int = 1, retain: bool = True, **kwargs: Any
    ) -> None:
        self._mqtt_client.publish(topic, payload, qos, retain, **kwargs)

    def set_target_temperature(self, temperature: int) -> None:
        if not (MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE):
            raise ValueError("Temperature out of bounds")
        self.publish(f"{self._apply_state_topic_prefix}temperature", str(temperature))

    def set_fan_mode(self, speed: FanMode) -> None:
        if self.state.preset_mode != PresetMode.HOME:
            # When setting a custom fan mode, clear away/party status if in those modes:
            self.set_preset_mode(PresetMode.HOME)
        self.publish(f"{self._apply_state_topic_prefix}fan", str(int(speed)))

    def apply_state(self, key: str, value: str) -> None:
        self.publish(f"{self._apply_state_topic_prefix}{key}", value)

    def set_preset_mode(self, preset_mode: PresetMode) -> None:
        if preset_mode == self.state.preset_mode:
            return

        match preset_mode:
            case PresetMode.HOME:
                self.apply_state("absent", "0")
                # 2 seems to disable party. 0 or 1 turns it on :shrug:
                self.apply_state("party", "2")
            case PresetMode.AWAY:
                self.apply_state("absent", "1")
            case PresetMode.BOOST:
                self.apply_state("party", "1")

    def _on_connect(
        self, client: MQTTClient, userdata: Any, flags: dict, rc: int
    ) -> None:
        if rc:
            _LOGGER.error("Failed to connect, return code %d", rc)
            return

        _LOGGER.debug("Connected, establishing subscription")
        self._mqtt_client.subscribe(f"{self._state_topic_prefix}#")

    def _on_message(self, client: MQTTClient, userdata: Any, msg: MQTTMessage) -> None:
        value = msg.payload.decode()
        _LOGGER.debug(
            f"Received MQTT message on topic [{msg.topic}] with payload [{value}]"
        )

        if not msg.topic.startswith(self._state_topic_prefix):
            # Not something we know
            return

        key = msg.topic[len(self._state_topic_prefix) :]

        def _propagate() -> None:
            # If we get data on the topic specific to our MAC, then the device is known to exist:
            if not self.device_is_discovered.is_set():
                self.device_is_discovered.set()

            match key:
                case "temperature":
                    self.state.temperature_target = int(value)
                case "status":
                    self.state.is_online = value == "online"
                    if self.state.is_online and not self.device_is_online.is_set():
                        self.device_is_online.set()

                case "fan" if value in ("1", "2", "3"):
                    self.state.fan_mode = FanMode(int(value))
                case "party":
                    # If enabling away while party is on, the physical display shows party disabled,
                    # the Ensy app shows it as enabled, while the state is broadcast as 2.
                    # So we use just 1 as enabled
                    if value == "1":
                        self.state.preset_mode = PresetMode.BOOST
                    else:
                        self.state.preset_mode = PresetMode.HOME
                case "absent":
                    # Ditto:
                    if value == "1":
                        self.state.preset_mode = PresetMode.AWAY
                    else:
                        self.state.preset_mode = PresetMode.HOME
                case "textr":
                    self.state.temperature_extract = int(value)
                case "texauh":
                    self.state.temperature_exhaust = int(value)
                case "tsupl":
                    self.state.temperature_supply = int(value)
                case "tout":
                    self.state.temperature_outside = int(value)
                case "overheating":
                    self.state.temperature_heater = int(value)
                case "he":
                    self.state.is_heating = value == "1"
                case _:
                    # We don't know or care, no need to cascade events
                    # E.g. what's `rm` and `altsa` etc? Alarms?
                    # No documentation and guesswork hasn't led anywhere so far.
                    return

            for callback in self.on_state_updated:
                callback(self.state)

        # Invoke any callbacks in the event loop thread:
        self.hass.loop.call_soon_threadsafe(_propagate)

    def _on_disconnect(self, *a: Any) -> None:
        _LOGGER.info("Disconnected")

        def _propagate() -> None:
            self.device_is_online.clear()
            self.state.is_online = False
            for callback in self.on_state_updated:
                callback("status", "offline", self.state)

        # Invoke any callbacks in the event loop thread:
        self.hass.loop.call_soon_threadsafe(_propagate)

    def _on_connect_fail(self, *a: Any) -> None:
        # Paho doesn't provide more details on why connection failed.
        # Historically, Ensy fails to rotate their TLS cert in time.
        _LOGGER.error("Failed to connect. Likely expired TLS certificate.")

    @staticmethod
    async def test_connectivity(
        hass: HomeAssistant, mac: str, allow_insecure_tls: bool = False
    ) -> bool:
        ensy_client = EnsyClient(hass, mac, allow_insecure_tls)
        await ensy_client.connect()
        try:
            async with hass.timeout.async_timeout(10):
                await ensy_client.device_is_discovered.wait()
                _LOGGER.info(
                    "Discovered Ensy device with MAC [{mac}] and confirmed upstream data is available"
                )
                return True
        except TimeoutError:
            _LOGGER.info(
                f"Discovered possible Ensy MAC address [{mac}], but timed out awaiting data from the MQTT endpoint"
            )
        except Exception:
            _LOGGER.exception(
                f"Discovered possible Ensy MAC address [{mac}], got unexpected exception testing connectivity"
            )
        finally:
            ensy_client.stop()
        return False
