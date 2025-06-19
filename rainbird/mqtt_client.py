import asyncio
import json

import aiohttp
import aiomqtt
import logging
import os
from dotenv import load_dotenv
from pyrainbird import async_client

load_dotenv()
logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler("rainbird.log"),
                logging.StreamHandler()
            ]
        )


class MqttClient:
    def __init__(
            self,
            broker_host: str,
            broker_port: int,
            section_count: int,
            controller: async_client.AsyncRainbirdController,
            discovery_prefix: str = "domoticz",
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.section_count = section_count
        self.rainbird_controller = controller
        self.discovery_prefix = discovery_prefix

        self.durations: dict[int, int] = {z: 15 for z in range(1, section_count + 1)}
        self.state: dict[int, bool] = {z: False for z in range(1, section_count + 1)}
        self.rain_sensor_state: bool = False
        self._lock = asyncio.Lock()
        self.update_interval = int(os.getenv("STATE_INTERVAL", 30))
        self.rain_delay_idx = int(os.getenv("RAIN_DELAY_IDX"))
        self.rain_delay_topic = os.getenv("RAIN_DELAY_COMMAND_TOPIC")
        self.pushover_user:str = os.getenv("PUSHOVER_USER")
        self.pushover_token:str = os.getenv("PUSHOVER_TOKEN")
        self.rain_delay_days: int = 0
        self.logger = logging.getLogger(__name__)
        self.names = {1: os.getenv("ZONE_1"), 2: os.getenv("ZONE_2"),
             3: os.getenv("ZONE_3"), 4: os.getenv("ZONE_4"),
             5: os.getenv("ZONE_5"), 6: os.getenv("ZONE_6"),
             7: os.getenv("ZONE_7"), 8: os.getenv("ZONE_8")}

    async def _publish_discovery(self, client: aiomqtt.Client):
        for z in range(1, self.section_count + 1):
            dimmer = {
                "platform": "light",
                "unique_id": f"rainbird_zone_{z}",
                "command_topic": f"rainbird/zone_{z}/switch/set",
                "state_topic": f"rainbird/zone_{z}/switch/state",
                "brightness_command_topic": f"rainbird/zone_{z}/duration/set",
                "brightness_state_topic": f"rainbird/zone_{z}/duration/state",
                "brightness_scale": 120,
                "payload_on": "ON",
                "payload_off": "OFF",
                "retain": True,
                "device": {
                    "identifiers": [f"rainbird_zone_{z}"],
                    "manufacturer": "RainBird",
                    "model": "ESP-Me",
                    "name": self.names.get(z)
                }
            }

            await client.publish(
                f"{self.discovery_prefix}/light/zone_{z}/config",
                json.dumps(dimmer),
                qos=1,
                retain=True
            )

        sensor = {
            "platform": "binary_sensor",
            "unique_id": "rainbird_rain_sensor",
            "state_topic": "rainbird/rain_sensor/state",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "moisture",
            "retain": True,
            "device": {
                "identifiers": ["rainbird_rain_sensor"],
                "manufacturer": "RainBird",
                "model": "ESP-Me",
                "name": "Rain Sensor"
            }
        }
        await client.publish(
            f"{self.discovery_prefix}/binary_sensor/rain_sensor/config",
            json.dumps(sensor),
            qos=1,
            retain=True
        )

    def _is_other_active(self, zone):
        return any(
            z != zone and self.state.get(z, False)
            for z in self.state
        )

    def _get_zone_and_data(self, topic: str, payload: str):
        topic = str(topic)
        topic_parts = topic.split("/")
        try:
            zone = int(topic_parts[1].split("_")[1])
        except (IndexError, ValueError):
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.logger.error("[ERROR] Invalid JSON payload")
            return
        return zone, data

    async def _handle_message(self, topic: str, payload: str):
        if topic.value == self.rain_delay_topic:
            local_days = int(float(payload))
            local_days = max(0, min(7, local_days))
            async with self._lock:
                try:
                    await self.rainbird_controller.set_rain_delay(local_days)
                    self.rain_delay_days = local_days
                    self.logger.info(f"Rain delay set to {local_days}")
                except Exception as e:
                    self.logger.error(f"[RAINBIRD_ERROR] Cannot set rain delay: {e}")
                    await self.send_pushover_message("[RAINBIRD_ERROR] Cannot set rain delay")
            return
        zone, data = self._get_zone_and_data(topic, payload)
        if "state" in data:
            self.state[zone] = False if data["state"] == "OFF" else True
            if data["state"] == "ON":
                await self._client.publish(
                    f"rainbird/zone_{zone}/duration/state",
                    str(self.durations[zone]),
                    retain=True
                )
            else:
                await self._client.publish(
                    f"rainbird/zone_{zone}/switch/state",
                    "OFF",
                    retain=True
                )
        elif "brightness" in data:
            duration = max(1, min(120, int(data["brightness"])))
            self.durations[zone] = duration
            await self._client.publish(
                f"rainbird/zone_{zone}/duration/state",
                str(duration),
                retain=True
            )
            if duration > 0:
                self.state[zone] = True
            else:
                self.state[zone] = False
        async with self._lock:
            if self.state[zone]:
                if not self._is_other_active(zone):
                    try:
                        await self.rainbird_controller.irrigate_zone(zone, self.durations[zone])
                        self.logger.info(f"[START] Irrigating zone {zone} for {self.durations[zone]} minutes")
                    except Exception as e:
                        self.logger.error(f"[RAINBIRD_ERROR] Cannot start irigation: {e}")
                        await self.send_pushover_message("[RAINBIRD_ERROR] Cannot start irigation")
                else:
                    self.logger.error(f"Cannot irrigate zone {zone}. Other zone is irrigating")
                    await self._client.publish(
                        f"rainbird/zone_{zone}/switch/state",
                        "OFF",
                        retain=True
                    )
            if self.durations[zone] == 0 or self.state[zone] is False:
                try:
                    self.logger.info(f"[STOP] Irrigating stopped")
                    await self.rainbird_controller.stop_irrigation()
                except Exception as e:
                    self.logger.error(f"[RAINBIRD_ERROR] Cannot stop irrigation: {e}")

    async def _poll_loop(self):
        while True:
            await asyncio.sleep(self.update_interval)
            async with self._lock:
                try:
                    states = await self.rainbird_controller.get_zone_states()
                    rain = await self.rainbird_controller.get_rain_sensor_state()
                    rain_delay = await self.rainbird_controller.get_rain_delay()
                except Exception as e:
                    self.logger.error(f"[RAINBIRD_ERROR] Cannot fetch data: {e}")
                    await self.send_pushover_message("[RAINBIRD_ERROR] Cannot fetch data")
                    continue
            if self.rain_delay_days != rain_delay:
                self.logger.info(f"[RAIN_DELAY] State changed to {rain_delay}")
                self.rain_delay_days = rain_delay
                dom_msg = {
                    "idx": self.rain_delay_idx,
                    "nvalue": 0,
                    "svalue": str(rain_delay)
                }
                await self._client.publish(
                    "domoticz/in",
                    json.dumps(dom_msg),
                    retain=True
                )
            if self.rain_sensor_state != rain:
                self.logger.info(f"[RAIN_SENSOR] State changed to {rain}")
                self.rain_sensor_state = rain
                payload = "ON" if self.rain_sensor_state else "OFF"
                await self._client.publish(
                    "rainbird/rain_sensor/state",
                    payload,
                    retain=True
                )
            active = states.active_set
            for z in range(1, self.section_count + 1):
                if z in active and not self.state[z]:
                    dur = self.durations.get(z, 15)
                    self.logger.info(f"[DETECT] External start zone {z} → {dur}min")
                    await self._client.publish(
                        f"rainbird/zone_{z}/duration/state",
                        str(dur), retain=True
                    )
                    self.state[z] = True
                elif z not in active and self.state[z]:
                    self.logger.info(f"[DETECT] External stop zone {z}")
                    await self._client.publish(
                        f"rainbird/zone_{z}/switch/state",
                        "OFF", retain=True
                    )
                    self.state[z] = False

    async def syncronise_state(self):
        try:
            self.rain_sensor_state = await self.rainbird_controller.get_rain_sensor_state()
            self.rain_delay_days = await self.rainbird_controller.get_rain_delay()
        except Exception as e:
            self.logger.error(f"[RAINBIRD_ERROR] Cannot fetch data: {e}")
        dom_msg = {
            "idx": self.rain_delay_idx,
            "nvalue": 0,
            "svalue": str(self.rain_delay_days)
        }
        await self._client.publish(
            "domoticz/in",
            json.dumps(dom_msg),
            retain=True
        )
        await self._client.publish(
            "rainbird/rain_sensor/state",
            "ON" if self.rain_sensor_state else "OFF",
            retain=True
        )

    async def _listen_loop(self, client):
        for z in range(1, self.section_count + 1):
            await client.subscribe(f"rainbird/zone_{z}/duration/set")
            await client.subscribe(f"rainbird/zone_{z}/switch/set")

        async for message in client.messages:
            topic = message.topic
            payload = message.payload.decode()
            await self._handle_message(topic, payload)
    async def send_pushover_message(self, message: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": self.pushover_token,
                        "user": self.pushover_user,
                        "title": "RainBird Notification",
                        "message": message
                    }
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    self.logger.error(f"Failed to send push: {response.status} - {text}")
                else:
                    self.logger.info("[PUSH] Push notification sent.")

    async def run(self):
        async with aiomqtt.Client(self.broker_host) as client:
            self._client = client
            await self._publish_discovery(client)
            await self.send_pushover_message("RainBird controller for domoticz started successfully")
            await self.syncronise_state()
            for z in range(1, self.section_count + 1):
                await self._client.publish(
                    f"rainbird/zone_{z}/switch/state",
                    "OFF",
                    retain=True
                )
            asyncio.create_task(self._poll_loop())

            for z in range(1, self.section_count + 1):
                await client.subscribe(f"rainbird/zone_{z}/duration/set")
                await client.subscribe(f"rainbird/zone_{z}/switch/set")
            await client.subscribe(self.rain_delay_topic)

            async for message in client.messages:
                topic = message.topic
                payload = message.payload.decode()
                await self._handle_message(topic, payload)


async def main():
    async with aiohttp.ClientSession() as client:
        controller: async_client.AsyncRainbirdController = async_client.CreateController(
            client,
            os.getenv("RAINBIRD_HOST"),
            os.getenv("RAINBIRD_PASSWORD")
        )
        await controller.stop_irrigation()
        mqtt_handler = MqttClient(
            broker_host=os.getenv("MQTT_BROKER_HOST"),
            broker_port=int(os.getenv("MQTT_BROKER_PORT", 1883)),
            section_count=len((await controller.get_available_stations()).active_set),
            controller=controller,
            discovery_prefix=os.getenv("DISCOVERY_PREFIX", "domoticz"),
        )
        await mqtt_handler.run()


if __name__ == "__main__":
    asyncio.run(main())
