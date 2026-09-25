"""Waveshare 4.2\" 400x300 e-Paper Rev 2.2 (SSD1683).

SPI protocol matches Waveshare Pico epd4in2_V2:
  - CS toggled per command / data byte (including framebuffer bytes)
  - SoftSPI byte-by-byte avoids ESP32-S3 bulk-write corruption
  - RAM window 0x44/0x45 for 400x300
  - Write 0x24 + 0x26, then 0x22/0x20 refresh
  - 0xF7 = full refresh, 0xC7 = fast refresh
"""

from machine import Pin, SoftSPI, SPI
from time import sleep_ms, ticks_ms, ticks_diff
import framebuf

import config

WIDTH = 400
HEIGHT = 300
BUF_SIZE = WIDTH * HEIGHT // 8  # 15000

# framebuf: 1 = pixel on; Waveshare RAM: 1/0xFF = white, 0 = black
BLACK = 0
WHITE = 1


class EPD:
    def __init__(self):
        self.width = WIDTH
        self.height = HEIGHT
        self.cs = Pin(config.EPD_CS, Pin.OUT, value=1)
        self.dc = Pin(config.EPD_DC, Pin.OUT, value=0)
        self.rst = Pin(config.EPD_RST, Pin.OUT, value=1)
        self.busy = Pin(config.EPD_BUSY, Pin.IN, Pin.PULL_UP)

        baud = getattr(config, "SPI_BAUD", 20_000)
        sck = Pin(config.SPI_SCK)
        mosi = Pin(config.SPI_MOSI)
        miso = Pin(config.SPI_MISO)
        if getattr(config, "SPI_USE_SOFT", True):
            self.spi = SoftSPI(
                baudrate=baud,
                polarity=0,
                phase=0,
                sck=sck,
                mosi=mosi,
                miso=miso,
            )
        else:
            self.spi = SPI(
                getattr(config, "SPI_ID", 1),
                baudrate=baud,
                polarity=0,
                phase=0,
                sck=sck,
                mosi=mosi,
                miso=miso,
            )
        self._byte = bytearray(1)

        self.buffer = bytearray(BUF_SIZE)
        self.fb = framebuf.FrameBuffer(self.buffer, WIDTH, HEIGHT, framebuf.MONO_HLSB)
        self.init()

    def _send_byte(self, value):
        self._byte[0] = value & 0xFF
        self.spi.write(self._byte)

    def send_command(self, command):
        self.dc(0)
        self.cs(0)
        self._send_byte(command)
        self.cs(1)

    def send_data(self, data):
        self.dc(1)
        self.cs(0)
        self._send_byte(data)
        self.cs(1)

    def send_data_buf(self, buf):
        """Send framebuffer byte-by-byte (CS toggled per byte)."""
        for v in buf:
            self.send_data(v)

    def reset(self):
        # Waveshare-style multi pulse — helps unstable USB power
        for _ in range(3):
            self.rst(1)
            sleep_ms(20)
            self.rst(0)
            sleep_ms(2)
        self.rst(1)
        sleep_ms(20)

    def wait_idle(self, timeout_ms=60000, arm_ms=400):
        """Wait until the panel is idle (BUSY low).

        SSD1683 raises BUSY a few milliseconds after reset, software reset,
        or a refresh. Sampling immediately can still see low, so the caller
        continues and deep-sleep aborts the waveform — the glass keeps a
        snowy frame. Wait for BUSY to rise, then fall.
        """
        t = 0
        while self.busy.value() == 0 and t < arm_ms:
            sleep_ms(10)
            t += 10
        t = 0
        while self.busy.value() == 1:
            sleep_ms(20)
            t += 20
            if t >= timeout_ms:
                raise OSError("BUSY timeout — check 5V/GND/SPI wires")

    def _set_ram_pointer(self):
        self.send_command(0x4E)
        self.send_data(0x00)
        self.send_command(0x4F)
        self.send_data(0x00)
        self.send_data(0x00)

    def init(self):
        import wifi

        wifi.pause_for_display()
        try:
            self._init_panel()
        finally:
            wifi.resume_after_display()

    def _init_panel(self):
        self.reset()
        self.wait_idle(10000)

        self.send_command(0x12)  # SWRESET
        self.wait_idle(10000)

        self.send_command(0x21)  # Display update control
        self.send_data(0x40)
        self.send_data(0x00)

        self.send_command(0x3C)  # Border waveform — 0x01 white (0x05 often leaves a black top bar)
        self.send_data(0x01)

        self.send_command(0x11)  # Data entry mode
        self.send_data(0x03)  # X+, Y+, horizontal

        # X: 0 .. 49 (400/8 - 1 = 0x31)
        self.send_command(0x44)
        self.send_data(0x00)
        self.send_data(0x31)

        # Y: 0 .. 299 (0x012B)
        self.send_command(0x45)
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data(0x2B)
        self.send_data(0x01)

        self._set_ram_pointer()
        self.wait_idle(10000)

    def _refresh(self, mode=0xF7):
        # 0xF7 full (clears ghosting), 0xC7 fast.
        # A good 4.2" full refresh finishes in a few seconds (seen ~1.6s).
        # Stop at 15s so a hung waveform does not hold the USB rail for a minute.
        self.send_command(0x22)
        self.send_data(mode)
        self.send_command(0x20)
        t0 = ticks_ms()
        self.wait_idle(15000)
        print("e-Paper refresh %d ms" % ticks_diff(ticks_ms(), t0))

    def clear(self, color=WHITE):
        self.fb.fill(color)

    def _show_once(self, full=True):
        self._set_ram_pointer()
        self.send_command(0x24)
        self.send_data_buf(self.buffer)
        self._set_ram_pointer()
        self.send_command(0x26)
        self.send_data_buf(self.buffer)
        sleep_ms(10)
        self._refresh(0xF7 if full else 0xC7)

    def show(self, full=True):
        """Push buffer to panel. full=True → 0xF7; False → 0xC7 fast.

        STA WiFi is off for the transfer and waveform, then brought back.
        On BUSY timeout: wait for the supply to recover, re-init, retry once.
        """
        import wifi

        wifi.pause_for_display()
        try:
            last_err = None
            for attempt in range(2):
                try:
                    if attempt > 0:
                        print("e-Paper BUSY timeout — retry once")
                        sleep_ms(800)
                        self.init()
                    self._show_once(full)
                    return
                except OSError as e:
                    last_err = e
                    if "BUSY" not in str(e):
                        raise
            raise last_err
        finally:
            wifi.resume_after_display()

    def sleep(self):
        self.send_command(0x10)
        self.send_data(0x01)
        sleep_ms(100)

    def text(self, s, x, y, color=BLACK):
        self.fb.text(s, x, y, color)

    def text_scaled(self, s, x, y, scale=2, color=BLACK):
        """Draw default 8x8 font scaled up (e.g. scale=2 → 16x16)."""
        if scale <= 1:
            self.fb.text(s, x, y, color)
            return
        w = len(s) * 8
        h = 8
        tw = (w + 7) & ~7
        if tw == 0:
            return
        buf = bytearray(tw * h // 8)
        tmp = framebuf.FrameBuffer(buf, tw, h, framebuf.MONO_HLSB)
        tmp.fill(WHITE)
        tmp.text(s, 0, 0, color)
        for j in range(h):
            for i in range(w):
                if tmp.pixel(i, j) == color:
                    px = x + i * scale
                    py = y + j * scale
                    for dy in range(scale):
                        for dx in range(scale):
                            self.fb.pixel(px + dx, py + dy, color)

    def hline(self, x, y, w, color=BLACK):
        self.fb.hline(x, y, w, color)

    def draw_sparkline(self, values, x, y, w, h, color=BLACK):
        """Draw a simple temperature sparkline (no box — box looked like a black bar)."""
        if values is None or len(values) == 0:
            self.text("...", x + 6, y + max(2, h // 2 - 4), color)
            return
        if len(values) == 1:
            self.fb.pixel(x + w // 2, y + h // 2, color)
            return

        vmin = min(values)
        vmax = max(values)
        if vmax - vmin < 0.2:
            mid = (vmin + vmax) / 2
            vmin = mid - 0.1
            vmax = mid + 0.1

        n = len(values)
        prev = None
        for i, v in enumerate(values):
            px = x + 1 + i * (w - 3) // (n - 1)
            py = y + h - 2 - int((v - vmin) * (h - 4) / (vmax - vmin))
            if py < y + 1:
                py = y + 1
            if py > y + h - 2:
                py = y + h - 2
            if prev is not None:
                self.fb.line(prev[0], prev[1], px, py, color)
            prev = (px, py)

    def show_dashboard(
        self,
        temp_c,
        humidity,
        press_hpa,
        status="OK",
        full=False,
        dew_c=None,
        comfort=None,
        trend=None,
        temp_history=None,
        clock_date=None,
        clock_time=None,
    ):
        """Draw sensor dashboard. full=True on first boot; False for routine updates."""
        self.clear(WHITE)
        title = getattr(config, "DASHBOARD_TITLE", "Temp Dash")
        date_s = clock_date or "--"
        time_s = clock_time or "--:--"

        # Top row: short title LEFT, large clock RIGHT (no overlap).
        self.text_scaled(title, 12, 8, 2, BLACK)
        # Right-align HH:MM (5 glyphs * 16px = 80)
        self.text_scaled(time_s, 400 - len(time_s) * 16 - 12, 8, 2, BLACK)
        # Date under title
        self.text(date_s, 12, 28, BLACK)

        # Left column (below clock/date)
        self.text("Temperature", 20, 52, BLACK)
        self.text_scaled("{:.1f} C".format(temp_c), 20, 64, 2, BLACK)

        self.text("Humidity", 20, 108, BLACK)
        self.text_scaled("{:.0f} %RH".format(humidity), 20, 120, 2, BLACK)

        self.text("Pressure", 20, 164, BLACK)
        self.text_scaled("{:.0f} hPa".format(press_hpa), 20, 176, 2, BLACK)

        # Right column
        self.text("Dew point", 210, 52, BLACK)
        if dew_c is None:
            self.text_scaled("--.- C", 210, 64, 2, BLACK)
        else:
            self.text_scaled("{:.1f} C".format(dew_c), 210, 64, 2, BLACK)

        self.text("Comfort", 210, 108, BLACK)
        self.text_scaled(comfort if comfort else "--", 210, 120, 2, BLACK)

        self.text("Trend", 210, 164, BLACK)
        self.text_scaled(trend if trend else "--", 210, 176, 2, BLACK)

        # Temperature sparkline
        hist = temp_history or []
        if len(hist) >= 2:
            label = "Temp hist {:.1f}-{:.1f}C".format(min(hist), max(hist))
        else:
            label = "Temp hist (warming up)"
        self.text(label, 20, 214, BLACK)
        self.draw_sparkline(hist, 20, 226, 360, 28, BLACK)

        # Footer: WiFi / setup — scale 2 only if it fits (setup text is long).
        footer = status if status else "WiFi --"
        scale = 2 if len(footer) <= 22 else 1
        y = 268 if scale == 2 else 275
        self.text_scaled(footer, 12, y, scale, BLACK)
        self.show(full=full)


def create_epd():
    return EPD()
