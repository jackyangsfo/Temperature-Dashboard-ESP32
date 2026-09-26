"""WiFi for the dashboard.

Connects with saved credentials (wifi.json, else config.py).
If that fails (or keeps failing after a home WiFi change), opens a phone
setup hotspot and a page at http://192.168.4.1.
"""

import json
import network
import socket
import time

import config

_CRED_PATH = "wifi.json"

_wlan = None
_ap = None
_http = None
_dns = None
_state = "off"  # off, connecting, ok, fail, portal
_attempt_ms = 0
_fail_ms = 0
_ever_ok = False
_fail_count = 0
_dirty = False
_quiet_reconnect = False
_ap_name = ""
_ssid = ""
_password = ""
_display_pause_count = 0
_last_ip = ""
_last_footer = ""


def _timeout_ms():
    return int(getattr(config, "WIFI_TIMEOUT_S", 20)) * 1000


def _retry_ms():
    return int(getattr(config, "WIFI_RETRY_S", 60)) * 1000


def _portal_after_fails():
    return int(getattr(config, "WIFI_PORTAL_AFTER_FAILS", 3))


def _load_creds():
    global _ssid, _password
    try:
        with open(_CRED_PATH) as f:
            data = json.load(f)
        ssid = data.get("ssid") or ""
        if ssid:
            _ssid = ssid
            _password = data.get("password") or ""
            return
    except OSError:
        pass
    _ssid = getattr(config, "WIFI_SSID", "") or ""
    _password = getattr(config, "WIFI_PASSWORD", "") or ""


def _save_creds(ssid, password):
    global _ssid, _password
    _ssid = ssid
    _password = password
    with open(_CRED_PATH, "w") as f:
        json.dump({"ssid": ssid, "password": password}, f)


def _mark_dirty():
    """Request a screen refresh, unless reconnecting after an e-paper update."""
    global _dirty
    if _quiet_reconnect:
        return
    _dirty = True


def consume_dirty():
    """True once after setup mode or link state changes (refresh the screen)."""
    global _dirty
    changed = _dirty
    _dirty = False
    return changed


def in_setup():
    return _state == "portal"


def is_connected():
    return _wlan is not None and _wlan.active() and _wlan.isconnected()


def ip_address():
    if is_connected():
        return _wlan.ifconfig()[0]
    return ""


def setup_name():
    return _ap_name or "TempDash"


def _ap_password():
    password = getattr(config, "WIFI_AP_PASSWORD", "") or "setup1234"
    if len(password) < 8:
        return "setup1234"
    return password


def _rssi_dbm():
    """Station RSSI in dBm, or None if unavailable."""
    try:
        if _wlan is not None and _wlan.active():
            return int(_wlan.status("rssi"))
    except Exception:
        pass
    return None


def _signal_bars(rssi):
    """ASCII signal meter for the e-paper footer (no IP)."""
    if rssi is None:
        return "WiFi [????]"
    if rssi >= -55:
        n = 4
    elif rssi >= -65:
        n = 3
    elif rssi >= -75:
        n = 2
    elif rssi >= -85:
        n = 1
    else:
        n = 0
    return "WiFi [%s%s]" % ("#" * n, "-" * (4 - n))


def status_text():
    """Short ASCII line for the e-paper footer."""
    global _last_ip, _last_footer
    if in_setup():
        return "%s  pw %s" % (setup_name(), _ap_password())
    if is_connected():
        _last_ip = ip_address()
        _last_footer = _signal_bars(_rssi_dbm())
        return _last_footer
    # STA is briefly off during e-paper refresh; keep last signal for the footer.
    if _display_pause_count > 0 and _last_footer:
        return _last_footer
    if not _ssid:
        return "WiFi setup"
    if _state == "fail":
        return "WiFi fail"
    if _state == "connecting":
        return "WiFi ..."
    return "WiFi off"


def _hotspot_name():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    mac = sta.config("mac")
    return "TempDash-%02X%02X" % (mac[-2], mac[-1])


def _radio_off():
    for mode in (network.AP_IF, network.STA_IF):
        nic = network.WLAN(mode)
        if nic.active():
            try:
                nic.disconnect()
            except OSError:
                pass
            nic.active(False)
    time.sleep_ms(300)


def _close(sock):
    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass


def _stop_portal():
    global _http, _dns, _ap
    _close(_http)
    _close(_dns)
    _http = None
    _dns = None
    if _ap is not None:
        _ap.active(False)
        _ap = None


def start_portal():
    """Open a WPA2 hotspot and a setup page at http://192.168.4.1."""
    global _ap, _http, _dns, _state, _ap_name, _wlan
    if _state == "portal" and _ap is not None and _ap.active():
        return
    _stop_portal()
    _ap_name = _hotspot_name()
    _radio_off()
    _wlan = None

    _ap = network.WLAN(network.AP_IF)
    _ap.active(False)
    time.sleep_ms(100)
    _ap.active(True)
    # WPA2 so phones list it. Open hotspots are often hidden on iPhone/Android.
    _ap.config(
        essid=_ap_name,
        password=_ap_password(),
        authmode=network.AUTH_WPA2_PSK,
        channel=6,
        hidden=False,
    )
    time.sleep_ms(200)
    print("AP on", _ap.active(), _ap.config("essid"), _ap.ifconfig()[0])

    _http = socket.socket()
    _http.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _http.bind(("0.0.0.0", 80))
    _http.listen(2)
    _http.setblocking(False)

    _dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _dns.bind(("0.0.0.0", 53))
    _dns.setblocking(False)

    _state = "portal"
    _mark_dirty()
    print("WiFi setup hotspot", _ap_name)
    print("Phone: join it, open http://192.168.4.1")


def pause_for_display():
    """Turn off STA while the e-paper runs its high-current refresh.

    A connected radio plus the panel waveform drops USB 5V. Init can still
    finish, then BUSY stays high and the glass never updates. Nested calls
    (init, then show) keep the radio off until the outer resume.
    """
    global _display_pause_count
    if in_setup():
        return
    if _display_pause_count == 0:
        if _wlan is None or not _wlan.active():
            return
        print("WiFi paused for e-paper")
        try:
            _wlan.disconnect()
        except OSError:
            pass
        _wlan.active(False)
        time.sleep_ms(400)
    _display_pause_count += 1


def resume_after_display():
    """Reconnect STA after the panel refresh, if it was paused."""
    global _display_pause_count, _state, _quiet_reconnect
    if _display_pause_count == 0:
        return
    _display_pause_count -= 1
    if _display_pause_count > 0:
        return
    _state = "off"
    # Reconnect quietly — do not force another e-paper refresh / page flip.
    _quiet_reconnect = True
    start()


def start():
    """Load credentials and begin STA, or open the phone setup page."""
    global _wlan, _state, _attempt_ms, _fail_count, _quiet_reconnect
    _load_creds()
    if not _ssid:
        _quiet_reconnect = False
        print("No saved WiFi — opening phone setup")
        start_portal()
        return False

    _stop_portal()
    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        _state = "ok"
        _fail_count = 0
        _mark_dirty()
        _quiet_reconnect = False
        print("WiFi OK", _wlan.ifconfig()[0])
        return True

    print("WiFi connecting to", _ssid)
    _wlan.connect(_ssid, _password)
    _state = "connecting"
    _attempt_ms = time.ticks_ms()
    _mark_dirty()
    return False


def _unquote(text):
    raw = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "+":
            raw.append(32)
            i += 1
        elif ch == "%" and i + 2 < len(text):
            try:
                raw.append(int(text[i + 1 : i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
            raw.append(ord(ch))
            i += 1
        else:
            raw.append(ord(ch) & 0xFF)
            i += 1
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        return raw.decode("utf-8", "ignore")


def _form_fields(body):
    fields = {}
    for part in body.split("&"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[_unquote(key)] = _unquote(value)
    return fields


_PAGE = """<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temp Dashboard</title>
</head><body>
<h2>Temperature Dashboard</h2>
<p>Enter your home WiFi. 2.4 GHz only.</p>
<form method="POST" action="/save">
<label>WiFi name<br><input name="ssid" required></label><br><br>
<label>Password<br><input name="password" type="password"></label><br><br>
<button type="submit">Save and connect</button>
</form>
</body></html>
"""

_DONE = """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved</title></head><body>
<h2>Saved</h2>
<p>The device is joining your WiFi. You can disconnect from this hotspot.</p>
</body></html>
"""


def _http_send(client, code, body):
    payload = body.encode("utf-8")
    header = (
        "HTTP/1.1 %s\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: %d\r\n\r\n"
        % (code, len(payload))
    )
    client.send(header.encode("utf-8") + payload)


def _handle_http(client):
    client.settimeout(3)
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 4096:
        chunk = client.recv(512)
        if not chunk:
            break
        data += chunk
    header, _, rest = data.partition(b"\r\n\r\n")
    text = header.decode("utf-8", "ignore")
    line = text.split("\r\n", 1)[0]
    parts = line.split(" ")
    method = parts[0] if parts else ""
    path = parts[1] if len(parts) > 1 else "/"
    length = 0
    for row in text.split("\r\n"):
        if row.lower().startswith("content-length:"):
            try:
                length = int(row.split(":", 1)[1].strip())
            except ValueError:
                length = 0
    body = rest
    while len(body) < length and len(body) < 2048:
        chunk = client.recv(512)
        if not chunk:
            break
        body += chunk
    if method == "POST" and path.startswith("/save"):
        fields = _form_fields(body.decode("utf-8", "ignore"))
        ssid = (fields.get("ssid") or "").strip()
        password = fields.get("password") or ""
        if ssid:
            _save_creds(ssid, password)
            print("WiFi saved for", ssid)
            _http_send(client, "200 OK", _DONE)
            client.close()
            start()
            return
        _http_send(client, "400 Bad Request", _PAGE)
    else:
        _http_send(client, "200 OK", _PAGE)
    client.close()


def _poll_http():
    if _http is None:
        return
    try:
        client, _addr = _http.accept()
    except OSError:
        return
    try:
        _handle_http(client)
    except OSError as exc:
        print("Setup page error:", exc)
        try:
            client.close()
        except OSError:
            pass


def _dns_reply(query):
    if len(query) < 12:
        return None
    end = 12
    while end < len(query) and query[end] != 0:
        end += query[end] + 1
        if end > len(query):
            return None
    end += 5  # null + type + class
    if end > len(query):
        return None
    question = query[12:end]
    answer = (
        b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04"
        + bytes((192, 168, 4, 1))
    )
    return query[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + question + answer


def _poll_dns():
    if _dns is None:
        return
    try:
        query, addr = _dns.recvfrom(512)
    except OSError:
        return
    reply = _dns_reply(query)
    if reply:
        try:
            _dns.sendto(reply, addr)
        except OSError:
            pass


def poll():
    """Advance WiFi. Call often; call more often while in_setup() is true."""
    global _state, _fail_ms, _ever_ok, _fail_count

    if in_setup():
        _poll_dns()
        _poll_http()
        return False

    if is_connected():
        global _quiet_reconnect
        if _state != "ok":
            print("WiFi OK", ip_address())
            _mark_dirty()
        _state = "ok"
        _ever_ok = True
        _fail_count = 0
        _quiet_reconnect = False
        return True

    now = time.ticks_ms()
    if _state == "connecting":
        if time.ticks_diff(now, _attempt_ms) > _timeout_ms():
            _fail_count += 1
            limit = _portal_after_fails()
            print("WiFi timeout (%d/%d)" % (_fail_count, limit))
            # First boot with bad/missing creds, or home WiFi changed:
            # open phone setup after enough consecutive failures.
            if (not _ever_ok) or _fail_count >= limit:
                print("Opening phone setup hotspot")
                _fail_count = 0
                start_portal()
            else:
                _state = "fail"
                _fail_ms = now
                _mark_dirty()
        return False

    if _state == "fail" and time.ticks_diff(now, _fail_ms) > _retry_ms():
        start()
    return False
