"""Read and set the Pi's IP address (fixed or automatic) through NetworkManager.

    status()                       -> current connection, address, mode
    apply("static", ip=..., gateway=..., dns=[...], prefix=24)
    apply("dhcp")

Changes go to the active connection (Wi-Fi or Ethernet) with nmcli. After a
change the connection is brought up again (a few seconds' drop) and checked:
if the Pi can't reach the router at the new address within the timeout, the
old settings are put back, so a typo can't strand it off the network.

Wi-Fi power saving is turned off on the connection (the Pi's Wi-Fi chip is
known to stop answering on the network when it naps), and watch() runs in the
background: it pings the router, writes drops to ~/labelbox/network.log and
reconnects the Wi-Fi if the router stays out of reach.

The app keeps the choice in its settings too and calls ensure() at start-up,
because with power-off protection on, NetworkManager's own files are reset
at every restart.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import subprocess
import threading
import time

TIMEOUT = 20


class NetError(Exception):
    """Raised with a message that can go straight on the screen."""


def _run(args, timeout=TIMEOUT):
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise NetError("NetworkManager (nmcli) isn't available on this system") from e
    except subprocess.TimeoutExpired as e:
        raise NetError("NetworkManager didn't answer") from e
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        msg = msg[-1] if msg else f"nmcli failed ({r.returncode})"
        if "Not authorized" in msg or "not authorized" in msg:
            msg = "Not allowed to change the network. Run once: sudo bash ~/labelbox/kiosk/allow-power.sh"
        raise NetError(msg.replace("Error: ", ""))
    return r.stdout


def _default_device():
    try:
        out = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True,
                             text=True, timeout=5).stdout.split()
        return out[out.index("dev") + 1] if "dev" in out else None
    except Exception:  # noqa: BLE001
        return None


def status() -> dict:
    """{'device','connection','type','method','ip','prefix','gateway','dns'} for the
    connection carrying the default route (or the first active one)."""
    dev = _default_device()
    if not dev:
        for line in _run(["-t", "-f", "DEVICE,TYPE,STATE", "device"]).splitlines():
            d, t, st = (line.split(":") + ["", "", ""])[:3]
            if st == "connected" and t in ("wifi", "ethernet"):
                dev = d
                break
    if not dev:
        return {"device": None, "connection": None, "type": None, "method": None,
                "ip": None, "prefix": None, "gateway": None, "dns": []}
    info = {}
    for line in _run(["-t", "-f", "GENERAL.CONNECTION,GENERAL.TYPE,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                      "device", "show", dev]).splitlines():
        key, _, val = line.partition(":")
        info.setdefault(key.split("[")[0], []).append(val.replace("\\:", ":"))
    con = (info.get("GENERAL.CONNECTION") or [""])[0] or None
    addr = (info.get("IP4.ADDRESS") or [""])[0]
    ip, prefix = (addr.split("/") + [None])[:2] if addr else (None, None)
    method = None
    if con:
        try:
            method = _run(["-g", "ipv4.method", "connection", "show", con]).strip()
        except NetError:
            pass
    return {"device": dev, "connection": con,
            "type": {"wifi": "Wi-Fi", "ethernet": "Ethernet"}.get(
                (info.get("GENERAL.TYPE") or [""])[0], (info.get("GENERAL.TYPE") or [""])[0]),
            "method": "static" if method == "manual" else ("dhcp" if method == "auto" else method),
            "ip": ip, "prefix": int(prefix) if prefix else None,
            "gateway": (info.get("IP4.GATEWAY") or [""])[0] or None,
            "dns": [d for d in info.get("IP4.DNS", []) if d]}


def check_static(ip: str, gateway: str, prefix: int = 24, dns=()) -> str | None:
    """A message describing what's wrong with these numbers, or None if they're fine."""
    try:
        addr = ipaddress.IPv4Address(ip.strip())
    except ValueError:
        return "The IP address isn't valid (four numbers 0-255, like 192.168.1.50)"
    try:
        gw = ipaddress.IPv4Address(gateway.strip())
    except ValueError:
        return "The router address isn't valid"
    for d in dns:
        try:
            ipaddress.IPv4Address(d.strip())
        except ValueError:
            return f"The DNS server {d!r} isn't valid"
    net = ipaddress.IPv4Network(f"{addr}/{prefix}", strict=False)
    if gw not in net:
        return f"The router {gw} isn't on the same network as {addr}/{prefix}"
    if addr in (net.network_address, net.broadcast_address):
        return f"{addr} can't be used: it's the network's own address"
    if addr == gw:
        return "The IP address can't be the same as the router's"
    return None


def address_in_use(ip: str, mine: str | None) -> bool:
    """True if something other than this Pi answers a ping at ip."""
    if ip == mine:
        return False
    try:
        return subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True,
                              timeout=4).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _settings_args(mode, ip=None, gateway=None, dns=(), prefix=24):
    if mode == "static":
        return ["ipv4.method", "manual", "ipv4.addresses", f"{ip}/{prefix}",
                "ipv4.gateway", gateway, "ipv4.dns", " ".join(dns) or gateway,
                "ipv4.ignore-auto-dns", "yes"]
    return ["ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", "",
            "ipv4.dns", "", "ipv4.ignore-auto-dns", "no"]


def _reachable(gateway, want_ip, dev, wait):
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            st = status()
            if st["ip"] and (want_ip is None or st["ip"] == want_ip):
                gw = gateway or st["gateway"]
                if gw and subprocess.run(["ping", "-c", "1", "-W", "1", "-I", dev or st["device"], gw],
                                         capture_output=True, timeout=4).returncode == 0:
                    return st
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return None


def apply(mode: str, ip=None, gateway=None, dns=(), prefix=None, wait=25) -> dict:
    """Switch the active connection to a fixed address or to DHCP, bring it up
    again and check it works. Returns the new status; on failure the previous
    settings are restored and NetError is raised."""
    before = status()
    con, dev = before["connection"], before["device"]
    if not con:
        raise NetError("No active network connection to change")
    prefix = prefix or before["prefix"] or 24
    if mode == "static":
        problem = check_static(ip, gateway, prefix, dns)
        if problem:
            raise NetError(problem)
        if address_in_use(ip, before["ip"]):
            raise NetError(f"Something else on the network already answers at {ip}. Pick another address")
    old = _run(["-g", "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.ignore-auto-dns",
                "connection", "show", con]).splitlines()
    old_args = ["ipv4.method", old[0], "ipv4.addresses", old[1], "ipv4.gateway", old[2],
                "ipv4.dns", old[3].replace(",", " "), "ipv4.ignore-auto-dns", old[4]] if len(old) >= 5 else None
    _run(["connection", "modify", con, *_settings_args(mode, ip, gateway, dns, prefix)])
    try:
        _run(["connection", "up", con], timeout=45)
    except NetError:
        pass                                   # checked below
    st = _reachable(gateway if mode == "static" else None, ip if mode == "static" else None, dev, wait)
    if st:
        return st
    if old_args:                               # put things back
        try:
            _run(["connection", "modify", con, *old_args])
            _run(["connection", "up", con], timeout=45)
        except NetError:
            pass
    raise NetError("Couldn't reach the router with those settings, so the old ones were put back")


def matches(saved: dict, st: dict) -> bool:
    """Is the connection already set up the way the saved choice says?"""
    if not saved or not st.get("connection"):
        return True
    if saved.get("mode") == "dhcp":
        return st.get("method") == "dhcp"
    return st.get("method") == "static" and st.get("ip") == saved.get("ip")


def ensure(saved: dict, wait_for_network=90) -> str | None:
    """At start-up: wait for a connection, then make it match the saved choice.
    Returns a short note for the screen if something was changed or failed."""
    end = time.monotonic() + wait_for_network
    st = None
    while time.monotonic() < end:
        try:
            st = status()
            if st["connection"]:
                break
        except NetError:
            pass
        time.sleep(2)
    if st and st["connection"] and powersave_off(st["connection"]) and matches(saved, st):
        try:
            _run(["connection", "up", st["connection"]], timeout=45)   # so it takes effect
        except NetError as e:
            log(f"reconnect after power-save change failed: {e}")
    if not st or not st["connection"] or matches(saved, st):
        return None
    try:
        if saved.get("mode") == "static":
            apply("static", saved.get("ip"), saved.get("gateway"), saved.get("dns") or (),
                  saved.get("prefix"))
            return f"Network: fixed address {saved.get('ip')}"
        apply("dhcp")
        return "Network: automatic address"
    except NetError as e:
        return f"Network setting not applied: {e}"


LOG = os.path.expanduser("~/labelbox/network.log")


def log(msg: str):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print("network:", msg, flush=True)
    try:
        lines = []
        if os.path.exists(LOG):
            with open(LOG) as f:
                lines = f.readlines()[-400:]
        lines.append(line + "\n")
        with open(LOG, "w") as f:
            f.writelines(lines)
    except OSError:
        pass


def powersave_off(con: str) -> bool:
    """Make sure Wi-Fi power saving is off for this connection. True if it had
    to be changed (it takes effect when the connection next comes up)."""
    try:
        if _run(["-g", "connection.type", "connection", "show", con]).strip() != "802-11-wireless":
            return False
        if _run(["-g", "802-11-wireless.powersave", "connection", "show", con]).strip() == "disable":
            return False
        _run(["connection", "modify", con, "802-11-wireless.powersave", "2"])
        log(f"turned Wi-Fi power saving off for {con}")
        return True
    except NetError as e:
        log(f"couldn't turn Wi-Fi power saving off: {e}")
        return False


def _link_info(dev):
    try:
        out = subprocess.run(["/usr/sbin/iw", "dev", dev, "link"], capture_output=True,
                             text=True, timeout=4).stdout
        keep = [l.strip() for l in out.splitlines()
                if l.strip().startswith(("Connected", "Not connected", "SSID", "freq", "signal"))]
        return "; ".join(keep) or "no link info"
    except Exception:  # noqa: BLE001
        return "no link info"


def _ping(host, dev=None):
    args = ["ping", "-c", "1", "-W", "2"] + (["-I", dev] if dev else []) + [host]
    try:
        return subprocess.run(args, capture_output=True, timeout=5).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def watch(every=20, fails_before_fix=3, on_change=None):
    """Background loop: ping the router; after a few misses reconnect the Wi-Fi
    (first the connection, then the radio). Every drop and fix is logged."""
    def loop():
        misses, down_since, gateway, dev, con, tries = 0, None, None, None, None, 0
        while True:
            try:
                st = status()
                if st["gateway"]:
                    gateway, dev, con = st["gateway"], st["device"], st["connection"] or con
            except Exception:  # noqa: BLE001
                pass
            ok = bool(gateway) and _ping(gateway, dev)
            if ok:
                if down_since:
                    log(f"back online after {int(time.monotonic() - down_since)} s ({_link_info(dev)})")
                    if on_change:
                        on_change(True)
                misses, down_since, tries = 0, None, 0
            else:
                misses += 1
                if misses == 1:
                    down_since = time.monotonic()
                    log(f"router {gateway} not answering ({_link_info(dev or 'wlan0')})")
                    if on_change:
                        on_change(False)
                if misses >= fails_before_fix and (misses - fails_before_fix) % 6 == 0:
                    tries += 1
                    try:
                        if tries % 2 == 1 and con:
                            log(f"reconnecting {con}")
                            _run(["connection", "up", con], timeout=45)
                        else:
                            log("turning the Wi-Fi radio off and on")
                            _run(["radio", "wifi", "off"])
                            time.sleep(3)
                            _run(["radio", "wifi", "on"])
                    except NetError as e:
                        log(f"reconnect failed: {e}")
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="net-watch").start()
