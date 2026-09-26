# Temperature Dashboard (ESP32)

XIAO ESP32-S3 + BME280 + Waveshare 4.2" e-Paper — a standalone temperature / humidity / pressure dashboard with phone WiFi setup and GitHub OTA updates.

温湿度气压电子纸仪表盘：本地测温刷屏，手机配网，联网对时，可从 GitHub 远程更新固件。

**User manual (客户说明):** [User_Manual.md](User_Manual.md) · [User_Manual.pdf](User_Manual.pdf)

---

## Hardware

| Part | Role |
|------|------|
| Seeed XIAO ESP32-S3 | MicroPython controller (2.4 GHz WiFi only) |
| BME280 | Temperature, humidity, pressure (I2C, **3.3V**) |
| Waveshare 4.2" e-Paper Rev 2.2 | Display (SPI, prefer **5V** on VCC) |
| USB-C | Power |

### Wiring (summary)

**BME280:** `VIN→3V3`, `GND→GND`, `SDA→D4`, `SCL→D5`

**e-Paper:** `VCC→5V`, `GND→GND`, `DIN→D10`, `CLK→D8`, `CS→D9`, `DC→D3`, `RST→D2`, `BUSY→D1`

---

## Features

- Live temperature / humidity / pressure (display unit: °F by default)
- Dew point, comfort label, pressure trend, temperature sparkline
- Date / time via NTP after WiFi connects
- Second page: monthly calendar (pages alternate ~every 30 s)
- Phone captive portal for WiFi setup (`TempDash-XXXX` / `setup1234`)
- Re-opens setup hotspot ~1 minute after home WiFi fails
- Footer shows WiFi status + firmware version (e.g. `v1.1.1`)
- **OTA** from this public GitHub repo (does not overwrite WiFi credentials or `config.py`)

---

## How it works

```text
Boot
  → init BME280 + e-paper
  → start WiFi (wifi.json or setup hotspot)
  → loop:
       read sensors ~every 5 s
       refresh e-paper ~every 30 s (sensors ↔ calendar)
       if online: NTP sync; OTA check (once on connect, then ~daily)
```

| Data | Source |
|------|--------|
| Temp / RH / pressure | BME280 on device |
| Dew / comfort / trend | Local math (`metrics.py`) |
| Clock / calendar | NTP over WiFi |
| Firmware updates | GitHub `version.json` + listed `.py` files |
| WiFi password | Only on device in `wifi.json` (not in git) |

---

## Repository layout

```text
version.json              OTA manifest (version + file list)
User_Manual.md / .pdf     End-user instructions
esp32_backup/
  main.py                 Main loop
  config.py               Pins, intervals, timezone, OTA URL
  bme280.py / epaper.py   Sensors & display
  wifi.py / clock.py      WiFi portal + NTP
  metrics.py              Derived readings
  ota.py                  GitHub OTA client
  version.txt             Local firmware version
  wifi.json               Local credentials (gitignored)
```

---

## Customer WiFi setup (short)

1. Power on → footer shows `TempDash-XXXX  pw setup1234`
2. Phone joins that hotspot → open `http://192.168.4.1`
3. Enter home **2.4 GHz** SSID/password → Save
4. Footer shows `WiFi [####]` signal bars when connected (no IP)

Details and troubleshooting: [User_Manual.md](User_Manual.md)

---

## OTA (developers)

1. Edit firmware under `esp32_backup/`
2. Bump **`version.json`** (and `esp32_backup/version.txt`) to a higher version, e.g. `1.1.2`
3. `git push` to `master` on this public repo
4. Device checks on WiFi connect (and about once per day); downloads listed files; reboots

Protected (never OTA-overwritten): `wifi.json`, `config.py`

OTA URL is set in `config.py` as `OTA_BASE_URL` →  
`https://raw.githubusercontent.com/jackyangsfo/Temperature-Dashboard-ESP32/master`

---

## Flash / update from a PC

Requires [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html) and a free serial port (e.g. `COM4`):

```bash
python -m mpremote connect COM4 cp esp32_backup/main.py :main.py
python -m mpremote connect COM4 cp esp32_backup/epaper.py :epaper.py
# …copy other modules as needed…
python -m mpremote connect COM4 reset
```

Do **not** upload your personal `wifi.json` to a public machine image.

---

## Useful `config.py` knobs

| Setting | Default | Meaning |
|---------|---------|---------|
| `TEMP_UNIT` | `"F"` | Display °F or °C |
| `EPD_REFRESH_S` | `30` | E-paper refresh interval (seconds) |
| `CALENDAR_PAGE` | `True` | Alternate sensors / calendar |
| `TIMEZONE_OFFSET_HOURS` | `-7` | Local offset from UTC |
| `WIFI_PORTAL_AFTER_FAILS` | `2` | Failures before reopening setup AP |
| `OTA_ENABLED` | `True` | Allow GitHub updates |
| `OTA_CHECK_S` | `86400` | OTA poll interval when online |
| `OTA_RETRY_S` | `600` | Retry sooner after a failed OTA check |

---

## License / notes

- End-user WiFi credentials stay on-device only.
- This repo is public so devices can fetch OTA files without a token.
- Other private GitHub projects are unrelated and unchanged.
