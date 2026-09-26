"""OTA updater — pull firmware from a public GitHub raw tree.

Flow:
  1. GET {OTA_BASE_URL}/version.json
  2. Compare with local version.txt
  3. Download listed files to *.tmp, then replace
  4. Write version.txt and soft-reset

Does NOT update: wifi.json (credentials), config.py (user settings).
"""

import json
import time

import config

_VERSION_PATH = "version.txt"
_last_check_ms = 0


def local_version():
    try:
        with open(_VERSION_PATH) as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return str(getattr(config, "APP_VERSION", "0.0.0"))


def _parse_ver(text):
    parts = []
    for bit in str(text).strip().split("."):
        try:
            parts.append(int(bit))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _newer(remote, local):
    return _parse_ver(remote) > _parse_ver(local)


def _base_url():
    return (
        getattr(config, "OTA_BASE_URL", "")
        or "https://raw.githubusercontent.com/jackyangsfo/Temperature-Dashboard-ESP32/master"
    ).rstrip("/")


def _check_interval_ms():
    return int(getattr(config, "OTA_CHECK_S", 86400)) * 1000


def _http_get(url, timeout_s=30):
    """Return response body as bytes, or raise OSError."""
    try:
        import urequests as requests
    except ImportError:
        try:
            import requests
        except ImportError:
            return _http_get_ssl(url, timeout_s)

    resp = None
    try:
        resp = requests.get(url, timeout=timeout_s)
        if resp.status_code != 200:
            raise OSError("HTTP %s for %s" % (resp.status_code, url))
        data = resp.content
        if not data:
            raise OSError("Empty body for %s" % url)
        return data
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


def _http_get_ssl(url, timeout_s=30):
    """Minimal HTTPS GET when urequests is missing."""
    import socket
    import ssl

    if not url.startswith("https://"):
        raise OSError("Only https supported")
    rest = url[8:]
    host, _, path = rest.partition("/")
    path = "/" + path
    addr = socket.getaddrinfo(host, 443)[0][-1]
    sock = socket.socket()
    sock.settimeout(timeout_s)
    sock.connect(addr)
    try:
        ssock = ssl.wrap_socket(sock, server_hostname=host)
    except TypeError:
        ssock = ssl.wrap_socket(sock)
    try:
        req = (
            "GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: TempDashOTA\r\nConnection: close\r\n\r\n"
            % (path, host)
        )
        ssock.write(req.encode())
        buf = b""
        while True:
            chunk = ssock.read(1024)
            if not chunk:
                break
            buf += chunk
    finally:
        try:
            ssock.close()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    header, _, body = buf.partition(b"\r\n\r\n")
    status = header.split(b"\r\n", 1)[0]
    if b" 200 " not in status and not status.endswith(b" 200"):
        raise OSError("Bad status: %s" % status)
    if not body:
        raise OSError("Empty body for %s" % url)
    return body


def _write_atomic(dest, data):
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        import os

        try:
            os.remove(dest)
        except OSError:
            pass
        os.rename(tmp, dest)
    except OSError:
        # Some ports lack rename — copy then delete tmp
        with open(dest, "wb") as f:
            f.write(data)
        try:
            import os

            os.remove(tmp)
        except OSError:
            pass


def fetch_manifest():
    url = _base_url() + "/version.json"
    print("OTA check", url)
    raw = _http_get(url)
    return json.loads(raw.decode())


def apply_update(manifest):
    """Download all files then reboot. Returns True if reboot was requested."""
    files = manifest.get("files") or []
    if not files:
        print("OTA: no files in manifest")
        return False

    base = _base_url()
    downloaded = []
    for item in files:
        remote = item.get("remote") or item.get("path") or ""
        dest = item.get("dest") or remote.split("/")[-1]
        if not remote or not dest:
            continue
        if dest in ("wifi.json", "config.py", "version.txt"):
            print("OTA skip protected", dest)
            continue
        url = base + "/" + remote.lstrip("/")
        print("OTA get", dest)
        data = _http_get(url)
        downloaded.append((dest, data))

    if not downloaded:
        print("OTA: nothing downloaded")
        return False

    for dest, data in downloaded:
        _write_atomic(dest, data)
        print("OTA wrote", dest, len(data), "bytes")

    ver = str(manifest.get("version") or "0.0.0")
    with open(_VERSION_PATH, "w") as f:
        f.write(ver + "\n")
    print("OTA complete ->", ver, "; rebooting")
    time.sleep_ms(500)
    import machine

    machine.reset()
    return True


def check(force=False):
    """If online and a newer GitHub build exists, download and reboot.

    Returns:
      "updated" | "current" | "skip" | "error"
    """
    global _last_check_ms
    if not getattr(config, "OTA_ENABLED", True):
        return "skip"

    now = time.ticks_ms()
    if (
        not force
        and _last_check_ms
        and time.ticks_diff(now, _last_check_ms) < _check_interval_ms()
    ):
        return "skip"

    try:
        import wifi

        if not wifi.is_connected():
            return "skip"
    except Exception:
        return "skip"

    _last_check_ms = now
    local = local_version()
    try:
        manifest = fetch_manifest()
        remote = str(manifest.get("version") or "0.0.0")
        print("OTA local", local, "remote", remote)
        if not _newer(remote, local):
            return "current"
        apply_update(manifest)
        return "updated"
    except Exception as e:
        print("OTA error:", e)
        return "error"
