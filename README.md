# 🌧️ mqtt-rainbird

**Control your RainBird irrigation system via MQTT and Domoticz** — fully containerized and ready for smart home integration.

This project enables automation of RainBird ESP-Me zones through MQTT commands, allowing seamless control and monitoring from platforms like Domoticz or Home Assistant. It also supports rain sensor state reporting and optional push notifications via Pushover.


---

## 🔧 Features

- 🌱 Start/stop irrigation zones via MQTT
- ⏱️ Adjust zone durations with dimmer-style MQTT messages
- ☔ Rain sensor state tracking (binary sensor)
- 📡 Rain delay control via custom topic
- 🧠 Auto-synchronizes state with RainBird controller
- 📬 Optional Pushover alerts for failures or status
- 🔁 Periodic polling to detect external/manual activations

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/KD377/mqtt-rainbird.git
cd mqtt-rainbird
````

### 2. Configure environment

Create a `.env` file:

```env
MQTT_BROKER_HOST=mqtt5            # or your broker IP or hostname
MQTT_BROKER_PORT=1883
RAINBIRD_HOST=192.168.1.101       # your RainBird LAN IP
RAINBIRD_PASSWORD=xxxx            # RainBird controller password
RAIN_DELAY_COMMAND_TOPIC=rainbird/rain_delay/set
RAIN_DELAY_IDX=12                 # Domoticz idx for rain delay
PUSHOVER_USER=your_user_key       # optional
PUSHOVER_TOKEN=your_app_token     # optional
STATE_INTERVAL=30                 # polling interval in seconds
# zone names which will appear as switch names in domoticz
ZONE_1=Zone 1
ZONE_2=Zone 2
ZONE_3=Zone 3
ZONE_4=Zone 4
ZONE_5=Zone 5
ZONE_6=Zone 6
ZONE_7=Zone 7
ZONE_8=Zone 8
```

### 3. Build & run with Docker Compose

```bash
docker compose -f compose.yml up -d --build
```

### 4. MQTT Topics

| Purpose                  | Topic                          | Payload                |
| ------------------------ | ------------------------------ | ---------------------- |
| Turn zone on/off         | `rainbird/zone_X/switch/set`   | `{ "state": "ON" }`    |
| Set zone duration        | `rainbird/zone_X/duration/set` | `{ "brightness": 10 }` |
| Set rain delay (in days) | `rainbird/rain_delay/set`      | `1`, `3`, etc.         |
| Rain sensor state        | `rainbird/rain_sensor/state`   | `ON` / `OFF`           |

> Zone states and durations are published to `.../switch/state` and `.../duration/state`.

---

## 🧪 Domoticz Integration

This project is designed to publish/receive messages compatible with Domoticz MQTT Autodiscovery CLient Gateway with LAN

---

## 📦 Volumes

The container writes logs to `rainbird.log`. You can mount this file persistently in your Docker Compose:

```yaml
volumes:
  - ./rainbird.log:/app/rainbird.log
```

---

## 🔔 Optional: Pushover Alerts

To receive push notifications on errors or startup events:

* Get a free [Pushover](https://pushover.net) account
* Set `PUSHOVER_USER` and `PUSHOVER_TOKEN` in your `.env`

---

## 🛠 Requirements

* Python 3.11+
* Docker (for containerization)
* MQTT broker (e.g. Mosquitto)
* RainBird ESP-Me controller with network access

---

## 🧼 License

MIT License © 2024 [KD377](https://github.com/KD377)

---

## 💬 Feedback & Contributions
Thanks to [allenporter](https://github.com/allenporter) https://github.com/allenporter/pyrainbird.git  
Issues, PRs, and suggestions are welcome!
