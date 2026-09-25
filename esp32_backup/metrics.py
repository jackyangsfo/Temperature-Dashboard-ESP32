"""Derived metrics from BME280 readings (no extra hardware)."""

import math


def dew_point_c(temp_c, humidity):
    """Magnus formula dew point in °C."""
    rh = max(1.0, min(100.0, float(humidity)))
    t = float(temp_c)
    a = 17.62
    b = 243.12
    gamma = (a * t) / (b + t) + math.log(rh / 100.0)
    return (b * gamma) / (a - gamma)


def comfort_label(temp_c, humidity):
    """Short indoor comfort hint for the dashboard."""
    if humidity < 30:
        return "Too dry"
    if humidity > 70:
        return "Humid"
    if temp_c < 18:
        return "Chilly"
    if temp_c > 27:
        return "Warm"
    return "Comfort"


class PressureTrend:
    """Compare current pressure to previous sample."""

    def __init__(self, threshold_hpa=0.3):
        self._last = None
        self._threshold = threshold_hpa

    def update(self, press_hpa):
        if self._last is None:
            self._last = press_hpa
            return "--"
        delta = press_hpa - self._last
        self._last = press_hpa
        if delta > self._threshold:
            return "Up"
        if delta < -self._threshold:
            return "Down"
        return "Flat"


class TempHistory:
    """Ring of recent temperatures for the e-paper sparkline."""

    def __init__(self, maxlen=60):
        self._vals = []
        self._maxlen = maxlen

    def add(self, temp_c):
        self._vals.append(float(temp_c))
        if len(self._vals) > self._maxlen:
            del self._vals[0]

    def values(self):
        return self._vals
