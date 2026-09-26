"""XIAO ESP32-S3 temperature dashboard: BME280 + Waveshare 4.2\" Rev 2.2.

Wiring — BME280 (I2C, use 3.3V only):
  VIN->3V3  GND->GND  SDA->D4  SCL->D5

Wiring — Waveshare 4.2\" Rev 2.2 SPI:
  VCC->5V   GND->GND
  DIN->D10  CLK->D8  CS->D9  DC->D3  RST->D2  BUSY->D1
"""

from machine import Pin, I2C
from time import sleep, ticks_ms, ticks_diff

import config
from bme280 import BME280, find_bme280
from epaper import create_epd
from metrics import dew_point_c, comfort_label, PressureTrend, TempHistory
import wifi
import clock
import ota


def main():
    i2c = I2C(
        config.I2C_ID,
        sda=Pin(config.I2C_SDA),
        scl=Pin(config.I2C_SCL),
        freq=config.I2C_FREQ,
    )

    print("I2C scan:", [hex(a) for a in i2c.scan()])
    addr = find_bme280(i2c, config.BME280_ADDR_CANDIDATES)
    if addr is None:
        print("ERROR: no BME280 at 0x76/0x77 (chip_id 0x60).")
        return

    print("BME280 found at", hex(addr))
    print("App version", ota.local_version())
    sensor = BME280(i2c, address=addr)
    pressure_trend = PressureTrend()
    temp_history = TempHistory(getattr(config, "TEMP_HISTORY_LEN", 60))

    print(
        "Init e-Paper Rev %s (protocol V%d)..."
        % (getattr(config, "EPD_BOARD", "?"), config.EPD_REVISION)
    )
    epd = create_epd()
    print("e-Paper ready")
    wifi.start()

    last_epd_ms = 0
    last_read_ms = 0
    last_time_s = ""
    first = True
    have_reading = False
    # Always paint once after boot (WiFi IP or setup hotspot text).
    screen_pending = True
    page = 0  # 0 = sensors, 1 = calendar
    ota_tried_connect = False
    temp_c = press_hpa = humidity = dew = 0.0
    comfort = trend = ""

    while True:
        wifi.poll()
        # When NTP first succeeds, force a refresh so "--:--" is replaced.
        had_clock = clock.is_synced()
        if wifi.is_connected():
            clock.sync()
            # OTA after WiFi is up (once on connect, then on OTA_CHECK_S).
            if getattr(config, "OTA_CHECK_ON_CONNECT", True) and not ota_tried_connect:
                ota_tried_connect = True
                ota.check(force=True)
            else:
                ota.check(force=False)
        if clock.is_synced() and not had_clock:
            screen_pending = True
            print("Clock synced — refresh screen")

        now = ticks_ms()
        if wifi.consume_dirty():
            screen_pending = True

        if (
            ticks_diff(now, last_read_ms) >= config.READ_INTERVAL_S * 1000
            or not have_reading
        ):
            last_read_ms = now
            temp_c, press_hpa, humidity = sensor.read()
            dew = dew_point_c(temp_c, humidity)
            comfort = comfort_label(temp_c, humidity)
            trend = pressure_trend.update(press_hpa)
            have_reading = True
            print(
                "T={:.2f} C  P={:.2f} hPa  H={:.1f} %  Dew={:.1f} C  {}  {}  {}  {}".format(
                    temp_c,
                    press_hpa,
                    humidity,
                    dew,
                    comfort,
                    trend,
                    clock.format_calendar_line(),
                    wifi.status_text(),
                )
            )

        screen_due = have_reading and (
            screen_pending
            or ticks_diff(now, last_epd_ms) >= config.EPD_REFRESH_S * 1000
        )
        if screen_due:
            # Only scheduled refreshes advance the page carousel. Forced
            # refreshes (WiFi/NTP) keep the same page so we don't get stuck
            # on the calendar after a post-display WiFi reconnect.
            timer_due = ticks_diff(now, last_epd_ms) >= config.EPD_REFRESH_S * 1000
            temp_history.add(temp_c)
            # Capture before init/show — those pause STA.
            status = wifi.status_text()
            date_s = clock.format_date()
            time_s = clock.format_time()
            # Full refresh when the minute changes (fast mode can ghost digits).
            use_full = first or (time_s != last_time_s and time_s != "--:--")
            show_cal = getattr(config, "CALENDAR_PAGE", False) and page == 1
            mode = "full" if use_full else "fast"
            page_name = "calendar" if show_cal else "sensors"
            print(
                "Updating e-Paper (%s/%s) [%s] [%s %s]..."
                % (mode, page_name, status, date_s, time_s)
            )
            try:
                epd.init()
                ver = ota.local_version()
                if show_cal:
                    epd.show_calendar(
                        clock.month_info(),
                        status=status,
                        full=use_full,
                        clock_time=time_s,
                        app_version=ver,
                    )
                else:
                    epd.show_dashboard(
                        temp_c,
                        humidity,
                        press_hpa,
                        status=status,
                        full=use_full,
                        dew_c=dew,
                        comfort=comfort,
                        trend=trend,
                        temp_history=temp_history.values(),
                        clock_date=date_s,
                        clock_time=time_s,
                        app_version=ver,
                    )
                epd.sleep()
                last_epd_ms = now
                last_time_s = time_s
                first = False
                screen_pending = False
                # Advance page only on the normal refresh timer.
                if getattr(config, "CALENDAR_PAGE", False) and timer_due:
                    page = 1 - page
                print("e-Paper updated (next page=%d)" % page)
            except OSError as e:
                print("e-Paper error:", e)
                last_epd_ms = now
                screen_pending = False

        if wifi.in_setup():
            sleep(0.2)
        else:
            sleep(0.5 if screen_pending else config.READ_INTERVAL_S)


if __name__ == "__main__":
    main()
