"""OTA updater — pull firmware from a public GitHub raw tree.

Flow:
  1. GET {OTA_BASE_URL}/version.json
  2. Compare with local version.txt
  3. Download listed files to RAM, stage as *.ota, then commit
  4. Write version.txt and soft-reset

Does NOT update: wifi.json (credentials), config.py (user settings).
"""

import json
import time

import config

_VERSION_PATH = "version.txt"
_PROTECTED = ("wifi.json", "config.py", "version.txt")
_last_check_ms = 0
_last_error_ms = 0


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


def _retry_interval_ms():
    # After a failed check, wait this long before trying again (not a full day).
    return int(getattr(config, "OTA_RETRY_S", 600)) * 1000


def _safe_dest(name):
    """Allow only a flat filename (no path separators / traversal)."""
    dest = str(name or "").strip().replace("\\", "/")
    if not dest or "/" in dest or dest in (".", "..") or dest.startswith("."):
        return None
    if dest in _PROTECTED or dest.endswith(".ota") or dest.endswith(".tmp"):
        return None
    return dest


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


def _remove(path):
    try:
        import os

        os.remove(path)
    except OSError:
        pass


def _write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _commit_file(dest, staged):
    """Replace dest with staged file (best-effort atomic)."""
    import os

    try:
        try:
            os.remove(dest)
        except OSError:
            pass
        os.rename(staged, dest)
    except OSError:
        # rename missing — copy then delete staged
        with open(staged, "rb") as f:
            data = f.read()
        _write_bytes(dest, data)
        _remove(staged)


def fetch_manifest():
    url = _base_url() + "/version.json"
    print("OTA check", url)
    raw = _http_get(url)
    return json.loads(raw.decode())


def apply_update(manifest):
    """Download all files, stage, then commit and reboot.

    Staging keeps live *.py untouched until every payload is on flash as *.ota.
    Commit window is short (local FS only). version.txt is written last.
    """
    files = manifest.get("files") or []
    if not files:
        print("OTA: no files in manifest")
        return False

    base = _base_url()
    downloaded = []
    for item in files:
        remote = item.get("remote") or item.get("path") or ""
        dest = _safe_dest(item.get("dest") or remote.split("/")[-1])
        if not remote or not dest:
            print("OTA skip bad dest", item)
            continue
        url = base + "/" + remote.lstrip("/")
        print("OTA get", dest)
        data = _http_get(url)
        if not data:
            raise OSError("Empty download for %s" % dest)
        downloaded.append((dest, data))

    if not downloaded:
        print("OTA: nothing downloaded")
        return False

    # Phase 1 — stage beside live files (do not touch running modules yet).
    staged = []
    try:
        for dest, data in downloaded:
            path = dest + ".ota"
            _write_bytes(path, data)
            staged.append(path)
            print("OTA staged", path, len(data), "bytes")
    except Exception:
        for path in staged:
            _remove(path)
        raise

    # Phase 2 — commit staged -> live (short window).
    try:
        for dest, _data in downloaded:
            _commit_file(dest, dest + ".ota")
            print("OTA wrote", dest)
    except Exception:
        # Leave any remaining *.ota for a future retry / manual cleanup.
        print("OTA commit failed; live files may be mixed")
        raise

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
    global _last_check_ms, _last_error_ms
    if not getattr(config, "OTA_ENABLED", True):
        return "skip"

    now = time.ticks_ms()
    if not force:
        if _last_check_ms and time.ticks_diff(now, _last_check_ms) < _check_interval_ms():
            return "skip"
        if _last_error_ms and time.ticks_diff(now, _last_error_ms) < _retry_interval_ms():
            return "skip"

    try:
        import wifi

        if not wifi.is_connected():
            return "skip"
    except Exception:
        return "skip"

    local = local_version()
    try:
        manifest = fetch_manifest()
        remote = str(manifest.get("version") or "0.0.0")
        print("OTA local", local, "remote", remote)
        if not _newer(remote, local):
            _last_check_ms = now
            _last_error_ms = 0
            return "current"
        apply_update(manifest)
        # reset() normally does not return
        _last_check_ms = now
        _last_error_ms = 0
        return "updated"
    except Exception as e:
        print("OTA error:", e)
        _last_error_ms = now
        # Do not advance _last_check_ms — retry after OTA_RETRY_S, not a full day.
        return "error"
