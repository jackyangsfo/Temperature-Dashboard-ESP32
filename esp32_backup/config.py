# Seeed XIAO ESP32-S3 — Temperature Dashboard
# Waveshare 4.2" e-Paper Module Rev 2.2 (SSD1683 / V2 demo)

# --- BME280 I2C (Seeed defaults: D4=SDA, D5=SCL) ---
I2C_ID = 0
I2C_SDA = 5   # D4
I2C_SCL = 6   # D5
I2C_FREQ = 100_000

BME280_ADDR_CANDIDATES = (0x76, 0x77)
BME280_CHIP_ID = 0x60

# --- Waveshare 4.2" Rev 2.2 SPI ---
# Wiring (module needs proper power — try 5V first on VCC):
#   EPD VCC  -> 5V (or 3V3)
#   EPD GND  -> GND
#   EPD DIN  -> D10 (GPIO9) MOSI
#   EPD CLK  -> D8  (GPIO7) SCK
#   EPD CS   -> D9  (GPIO8)
#   EPD DC   -> D3  (GPIO4)
#   EPD RST  -> D2  (GPIO3)
#   EPD BUSY -> D1  (GPIO2)
# SoftSPI — very low rate; buffer is sent byte-by-byte (avoids SoftSPI bulk corruption)
SPI_BAUD = 20_000
SPI_USE_SOFT = True
SPI_ID = 1
SPI_SCK = 7    # D8
SPI_MOSI = 9   # D10
SPI_MISO = 1   # D0 unused (write-only panel)
EPD_CS = 8     # D9
EPD_DC = 4     # D3
EPD_RST = 3    # D2
EPD_BUSY = 2   # D1

# Rev 2.2 board uses V2 / SSD1683 protocol
EPD_REVISION = 2
EPD_BOARD = "2.2"

READ_INTERVAL_S = 5
EPD_REFRESH_S = 30
# Sparkline points (1 point per e-paper refresh ≈ 30 min when EPD_REFRESH_S=30)
TEMP_HISTORY_LEN = 60

# Shown on e-paper (ASCII only — default font has no Chinese glyphs)
DASHBOARD_TITLE = "Temp Dash"

# Temperature display unit: "C" (Celsius) or "F" (Fahrenheit).
# Sensor math always uses Celsius; only the e-paper numbers change.
TEMP_UNIT = "F"

# Second page: monthly calendar grid. Each e-paper refresh alternates
# sensors <-> calendar when True.
CALENDAR_PAGE = True

# --- Clock / calendar (NTP over WiFi) ---
# Local offset from UTC in hours. Examples: US Pacific -7 (PDT) / -8 (PST),
# China +8, Japan +9.
TIMEZONE_OFFSET_HOURS = -7
NTP_HOST = "pool.ntp.org"
NTP_SYNC_S = 3600  # re-sync about once per hour while online

# --- WiFi (ESP32-S3 is 2.4 GHz only) ---
# Phone setup: if these are empty and wifi.json is missing, the board opens
# hotspot TempDash-XXXX. Join it and open http://192.168.4.1
# Optional fallback if you upload credentials from a computer instead.
WIFI_SSID = ""
WIFI_PASSWORD = ""
WIFI_TIMEOUT_S = 15
WIFI_RETRY_S = 30
# After this many consecutive connect timeouts, reopen the phone setup hotspot
# so the customer can enter a new WiFi name/password without a PC.
# With timeout=15s and retry=30s: fail1 → wait → fail2 ≈ about 1 minute.
WIFI_PORTAL_AFTER_FAILS = 2
# Phone joins this password when the setup hotspot is on (at least 8 characters).
WIFI_AP_PASSWORD = "setup1234"

# --- OTA (GitHub raw) ---
# Board fetches version.json over WiFi and downloads listed .py files.
# Does not overwrite wifi.json or config.py (keeps customer settings).
OTA_ENABLED = True
APP_VERSION = "1.1.3"
OTA_BASE_URL = (
    "https://raw.githubusercontent.com/jackyangsfo/Temperature-Dashboard-ESP32/master"
)
# How often to check when online (seconds). Default: once per day.
OTA_CHECK_S = 86400
# After a failed OTA check, retry sooner than OTA_CHECK_S.
OTA_RETRY_S = 600
# Also check once shortly after WiFi first connects.
OTA_CHECK_ON_CONNECT = True
