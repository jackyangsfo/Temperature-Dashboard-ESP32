"""Minimal MicroPython BME280 driver (I2C).

Supports auto-detect of address 0x76 / 0x77 and chip ID check (0x60).
"""

from micropython import const
from ustruct import unpack, unpack_from
from time import sleep_ms

_REG_DIG_T1 = const(0x88)
_REG_DIG_H1 = const(0xA1)
_REG_DIG_H2 = const(0xE1)
_REG_CHIPID = const(0xD0)
_REG_RESET = const(0xE0)
_REG_CTRL_HUM = const(0xF2)
_REG_STATUS = const(0xF3)
_REG_CTRL_MEAS = const(0xF4)
_REG_CONFIG = const(0xF5)
_REG_DATA = const(0xF7)

_CHIP_ID = const(0x60)
_OSAMPLE_X1 = const(1)


def find_bme280(i2c, candidates=(0x76, 0x77)):
    """Return first address on the bus that looks like a BME280, else None."""
    found = i2c.scan()
    for addr in candidates:
        if addr in found:
            chip = i2c.readfrom_mem(addr, _REG_CHIPID, 1)[0]
            if chip == _CHIP_ID:
                return addr
    return None


class BME280:
    def __init__(self, i2c, address=None, candidates=(0x76, 0x77)):
        self.i2c = i2c
        if address is None:
            address = find_bme280(i2c, candidates)
            if address is None:
                raise OSError("BME280 not found (tried 0x76/0x77, chip_id=0x60)")
        self.address = address

        chip = self._read(_REG_CHIPID, 1)[0]
        if chip != _CHIP_ID:
            raise OSError("Unexpected chip id 0x%02x (want 0x60)" % chip)

        self._write(_REG_RESET, b"\xB6")
        sleep_ms(10)
        self._load_calibration()

        # Humidity oversampling must be set before ctrl_meas
        self._write(_REG_CTRL_HUM, bytes([_OSAMPLE_X1]))
        # Normal mode, temp/pressure oversampling x1
        self._write(_REG_CTRL_MEAS, bytes([(_OSAMPLE_X1 << 5) | (_OSAMPLE_X1 << 2) | 3]))
        self._write(_REG_CONFIG, b"\x00")
        sleep_ms(100)

    def _read(self, reg, n):
        return self.i2c.readfrom_mem(self.address, reg, n)

    def _write(self, reg, data):
        self.i2c.writeto_mem(self.address, reg, data)

    def _load_calibration(self):
        cal = self._read(_REG_DIG_T1, 26)
        (
            self.dig_T1,
            self.dig_T2,
            self.dig_T3,
            self.dig_P1,
            self.dig_P2,
            self.dig_P3,
            self.dig_P4,
            self.dig_P5,
            self.dig_P6,
            self.dig_P7,
            self.dig_P8,
            self.dig_P9,
            _,
            self.dig_H1,
        ) = unpack("<HhhHhhhhhhhhBB", cal)

        h = self._read(_REG_DIG_H2, 7)
        self.dig_H2 = unpack_from("<h", h, 0)[0]
        self.dig_H3 = h[2]
        e4 = unpack_from("<b", h, 3)[0]
        e5 = h[4]
        e6 = unpack_from("<b", h, 5)[0]
        self.dig_H4 = (e4 << 4) | (e5 & 0x0F)
        self.dig_H5 = (e6 << 4) | (e5 >> 4)
        self.dig_H6 = unpack_from("<b", h, 6)[0]

    def _wait_measuring(self):
        for _ in range(50):
            if (self._read(_REG_STATUS, 1)[0] & 0x08) == 0:
                return
            sleep_ms(10)
        raise OSError("BME280 measurement timeout")

    def read(self):
        """Return (temperature_C, pressure_hPa, humidity_pct) as floats."""
        self._wait_measuring()
        raw = self._read(_REG_DATA, 8)
        adc_p = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4)
        adc_t = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)
        adc_h = (raw[6] << 8) | raw[7]

        # Temperature (Bosch integer formula → °C)
        var1 = (((adc_t >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (
            ((((adc_t >> 4) - self.dig_T1) * ((adc_t >> 4) - self.dig_T1)) >> 12)
            * self.dig_T3
        ) >> 14
        t_fine = var1 + var2
        temp_c = ((t_fine * 5 + 128) >> 8) / 100.0

        # Pressure → Pa, then hPa
        var1 = t_fine - 128000
        var2 = var1 * var1 * self.dig_P6
        var2 = var2 + ((var1 * self.dig_P5) << 17)
        var2 = var2 + (self.dig_P4 << 35)
        var1 = (((var1 * var1 * self.dig_P3) >> 8) + ((var1 * self.dig_P2) << 12))
        var1 = (((1 << 47) + var1) * self.dig_P1) >> 33
        if var1 == 0:
            press_hpa = 0.0
        else:
            p = 1048576 - adc_p
            p = (((p << 31) - var2) * 3125) // var1
            var1 = (self.dig_P9 * (p >> 13) * (p >> 13)) >> 25
            var2 = (self.dig_P8 * p) >> 19
            press_pa = ((p + var1 + var2) >> 8) + (self.dig_P7 << 4)
            press_hpa = press_pa / 256.0 / 100.0

        # Humidity → %RH
        v_x1 = t_fine - 76800
        v_x1 = (
            (
                (
                    ((adc_h << 14) - (self.dig_H4 << 20) - (self.dig_H5 * v_x1))
                    + 16384
                )
                >> 15
            )
            * (
                (
                    (
                        (
                            (
                                ((v_x1 * self.dig_H6) >> 10)
                                * (((v_x1 * self.dig_H3) >> 11) + 32768)
                            )
                            >> 10
                        )
                        + 2097152
                    )
                    * self.dig_H2
                    + 8192
                )
                >> 14
            )
        )
        v_x1 = v_x1 - (((((v_x1 >> 15) * (v_x1 >> 15)) >> 7) * self.dig_H1) >> 4)
        v_x1 = 0 if v_x1 < 0 else v_x1
        v_x1 = 419430400 if v_x1 > 419430400 else v_x1
        humidity = (v_x1 >> 12) / 1024.0

        return temp_c, press_hpa, humidity
