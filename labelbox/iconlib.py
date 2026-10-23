"""Black-and-white icons for labels: search online, keep a local library.

Icons come from Iconify (https://iconify.design), a free collection of open
source icon sets, as SVG. Searching and the first download need internet;
after that an icon is drawn from the local copy.

    search("coffee")        -> ["mdi:coffee", "tabler:coffee", ...]
    fetch_many(ids)         -> {id: svg}       downloads in one request per set
    raster("mdi:coffee", 300) -> PIL "L" image, black on white
    save(id) / forget(id) / library()

Where things live:
    icon-library/           icons you've used (next to app.py)
    /boot/firmware/voicelabels-icons/   the same, kept on the boot partition
                            when power-off protection is on (see protect.sh)
    ~/.cache/voicelabels/   search results and downloaded icons
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

import config
from svgraster import svg_to_image

API = "https://api.iconify.design"
USER_AGENT = "VoiceLabels/1.0 (+https://github.com/ScottYates/VoiceLabels)"
LIBRARY = Path(__file__).with_name("icon-library")
BOOT_LIBRARY = Path("/boot/firmware/voicelabels-icons")
HELPER = "/usr/local/sbin/voicelabels-icon"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "voicelabels"
SEARCH_TTL = 30 * 24 * 3600
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$")
_lock = threading.Lock()


class IconError(Exception):
    """Raised with a message that can go straight on the screen."""


def valid(icon_id: str) -> bool:
    return bool(icon_id) and bool(ID_RE.match(icon_id))


def _fname(icon_id: str) -> str:
    return icon_id.replace(":", "__") + ".svg"


def _id_from(path: Path) -> str:
    return path.stem.replace("__", ":", 1)


def _http(url: str, limit: int = 2_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=getattr(config, "ICON_TIMEOUT_SECONDS", 8)) as r:
            data = r.read(limit + 1)
    except Exception as e:  # noqa: BLE001
        raise IconError("No internet connection. Saved icons still work.") from e
    if len(data) > limit:
        raise IconError("The icon service sent too much data")
    return data


# --- search ----------------------------------------------------------------

# Words people say, and what the icon sets call them. Each entry's searches
# run first, then the words as spoken. config.ICON_SYNONYMS adds more.
SYNONYMS = {
    # computer parts
    "ram": ["ram memory", "memory"],
    "memory": ["ram memory", "memory"],
    "video card": ["graphics card", "gpu"],
    "graphics card": ["graphics card", "gpu"],
    "gpu": ["graphics card", "gpu"],
    "network card": ["network interface card", "network interface", "ethernet"],
    "nic": ["network interface card", "network interface", "ethernet"],
    "network adapter": ["network interface card", "network interface", "ethernet"],
    "wifi card": ["wifi", "network interface card"],
    "cpu": ["cpu", "processor"],
    "processor": ["cpu", "processor"],
    "motherboard": ["motherboard", "circuit board"],
    "mainboard": ["motherboard", "circuit board"],
    "power supply": ["power supply"],
    "psu": ["power supply"],
    "ssd": ["ssd", "solid state"],
    "nvme": ["nvme", "ssd"],
    "m.2": ["nvme", "ssd"],
    "m2": ["nvme", "ssd"],
    "hard drive": ["hard drive", "hdd"],
    "hard disk": ["hard drive", "hdd"],
    "hdd": ["hdd", "hard drive"],
    "sata": ["hard drive", "hdd"],
    "heatsink": ["fan", "cpu"],
    "cooler": ["fan", "cpu"],
    "case fan": ["fan"],
    "sd card": ["sd card", "micro sd"],
    "micro sd": ["micro sd", "sd card"],
    "flash drive": ["usb flash drive", "usb drive", "usb"],
    "thumb drive": ["usb flash drive", "usb drive", "usb"],
    # cables and ports
    "usb c": ["usb c", "usb type c"],
    "usb-c": ["usb c", "usb type c"],
    "type c": ["usb c", "usb type c"],
    "usb cable": ["usb cable", "usb"],
    "hdmi": ["hdmi cable", "hdmi"],
    "hdmi cable": ["hdmi cable", "hdmi"],
    "displayport": ["displayport", "monitor"],
    "display port": ["displayport", "monitor"],
    "ethernet": ["ethernet cable", "ethernet"],
    "ethernet cable": ["ethernet cable", "ethernet"],
    "network cable": ["ethernet cable", "ethernet"],
    "cat 6": ["ethernet cable", "ethernet"],
    "cat6": ["ethernet cable", "ethernet"],
    "cat5": ["ethernet cable", "ethernet"],
    "power cable": ["power cable", "power plug"],
    "power cord": ["power cable", "power plug"],
    "audio cable": ["audio jack", "headphone jack", "jack"],
    "aux cable": ["audio jack", "headphone jack", "jack"],
    "headphone jack": ["headphone jack", "audio jack"],
    "video cable": ["hdmi cable", "displayport", "vga"],
    "serial cable": ["serial port", "serial"],
    "adapter": ["adapter", "usb"],
    "charger": ["charger", "power plug"],
    # 3D printing
    "filament": ["spool", "3d filament", "printer 3d nozzle"],
    "pla": ["spool", "3d filament"],
    "petg": ["spool", "3d filament"],
    "abs": ["spool", "3d filament"],
    "tpu": ["spool", "3d filament"],
    "3d printer": ["printer 3d", "3d printer"],
    "nozzle": ["printer 3d nozzle", "nozzle"],
    "resin": ["printer 3d", "bottle"],
    # hardware
    "screws": ["screw"],
    "nuts": ["nut", "bolt"],
    "bolts": ["bolt", "nut"],
    "nuts and bolts": ["nut", "bolt"],
    "washers": ["washer"],
}

# Faint or two-tone variants that print poorly, and near-duplicate copies.
_SKIP_PARTS = {"duotone", "thin", "light", "twotone", "duo", "broken"}


def _skip(icon_id: str) -> bool:
    prefix, name = icon_id.split(":", 1)
    parts = name.split("-")
    if _SKIP_PARTS & set(parts):
        return True
    if parts[-1] in ("off", "slash") or "off" in parts[1:]:   # crossed-out versions
        return True
    if prefix == "material-symbols" and name.endswith(("-rounded", "-sharp")):
        return True
    if prefix == "iconmind" and parts[-1] == "regular":       # keep the bold copy
        return True
    if prefix == "energy-icons" and "20" in parts:             # keep the large copy
        return True
    if prefix == "solar" and parts[-1] in ("linear", "outline"):
        return True
    return False


def search_terms(query: str) -> list[str]:
    q = " ".join(query.lower().replace("_", " ").split())[:60]
    if not q:
        return []
    table = dict(SYNONYMS)
    table.update({k.lower(): v for k, v in getattr(config, "ICON_SYNONYMS", {}).items()})
    terms = list(table.get(q, []))
    if q.endswith("s") and not q.endswith("ss") and len(q) > 3:   # "cables" -> "cable"
        terms += table.get(q[:-1], []) + [q[:-1]]
    terms.append(q)
    out = []
    for t in terms:
        if t not in out:
            out.append(t)
    return out


def search(query: str, limit: int = 140) -> list[str]:
    """Icon ids for what was said or typed, best matches first."""
    results: list[str] = []
    errors = 0
    terms = search_terms(query)
    for t in terms:
        try:
            ids = _search_one(t)
        except IconError:
            errors += 1
            continue
        for i in ids:
            if i not in results:
                results.append(i)
    if terms and errors == len(terms):
        raise IconError("No internet connection. Saved icons still work.")
    return results[:limit]


def _search_one(q: str) -> list[str]:
    sets = ",".join(getattr(config, "ICON_SETS", []))
    key = hashlib.sha1(f"{q}|{sets}".encode()).hexdigest()[:16]
    cached = CACHE / "search" / f"{key}.json"
    try:
        if time.time() - cached.stat().st_mtime < SEARCH_TTL:
            return json.loads(cached.read_text())
    except (OSError, ValueError):
        pass
    params = {"query": q, "limit": "120"}
    if sets:
        params["prefixes"] = sets
    data = json.loads(_http(f"{API}/search?{urllib.parse.urlencode(params)}"))
    ids = [i for i in data.get("icons", []) if valid(i) and not _skip(i)]
    _write(cached, json.dumps(ids))
    return ids


# --- getting the SVG ----------------------------------------------------------

def _cached_path(icon_id: str) -> Path:
    return CACHE / "svg" / _fname(icon_id)


def local_svg(icon_id: str) -> str | None:
    """The icon from the library or the download cache, without going online."""
    if not valid(icon_id):
        return None
    for p in (LIBRARY / _fname(icon_id), BOOT_LIBRARY / _fname(icon_id), _cached_path(icon_id)):
        try:
            return p.read_text()
        except OSError:
            continue
    return None


def _svg_from_json(data: dict, name: str) -> str | None:
    icons, aliases = data.get("icons", {}), data.get("aliases", {})
    tf = {}
    seen = 0
    while name not in icons and name in aliases and seen < 5:   # follow aliases
        a = aliases[name]
        for k in ("rotate", "hFlip", "vFlip"):
            if k in a:
                tf[k] = (tf.get(k, 0) + a[k]) if k == "rotate" else (bool(tf.get(k)) ^ bool(a[k]))
        name, seen = a.get("parent", ""), seen + 1
    icon = icons.get(name)
    if not icon or "body" not in icon:
        return None
    left, top = icon.get("left", data.get("left", 0)), icon.get("top", data.get("top", 0))
    w = icon.get("width", data.get("width", 16))
    h = icon.get("height", data.get("height", 16))
    body = icon["body"]
    for k in ("rotate", "hFlip", "vFlip"):
        if k in icon and k not in tf:
            tf[k] = icon[k]
    parts = []
    if tf.get("hFlip"):
        parts.append(f"translate({2 * left + w} 0) scale(-1 1)")
    if tf.get("vFlip"):
        parts.append(f"translate(0 {2 * top + h}) scale(1 -1)")
    r = int(tf.get("rotate", 0)) % 4
    if r:
        cx, cy = left + w / 2, top + h / 2
        parts.append(f"rotate({90 * r} {cx} {cy})")
    if parts:
        body = f'<g transform="{" ".join(parts)}">{body}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {top} {w} {h}">'
            f"{body}</svg>")


def fetch_many(ids: list[str]) -> dict[str, str]:
    """SVGs for these icons: local copies first, then one download per icon set."""
    out, need = {}, {}
    for i in ids:
        s = local_svg(i)
        if s:
            out[i] = s
        elif valid(i):
            prefix, name = i.split(":", 1)
            need.setdefault(prefix, []).append(name)
    for prefix, names in need.items():
        for start in range(0, len(names), 50):
            chunk = names[start:start + 50]
            url = f"{API}/{prefix}.json?icons={urllib.parse.quote(','.join(chunk), safe=',')}"
            try:
                data = json.loads(_http(url))
            except (IconError, ValueError):
                continue
            for n in chunk:
                svg = _svg_from_json(data, n)
                if svg:
                    out[f"{prefix}:{n}"] = svg
                    _write(_cached_path(f"{prefix}:{n}"), svg)
    return out


def get_svg(icon_id: str) -> str:
    s = local_svg(icon_id) or fetch_many([icon_id]).get(icon_id)
    if not s:
        raise IconError("Couldn't get that icon")
    return s


# --- drawing -----------------------------------------------------------------

@lru_cache(maxsize=256)
def _raster(icon_id: str, px: int, svg: str):
    return svg_to_image(svg, px)


def raster(icon_id: str, px: int):
    """The icon as a px x px black-on-white image, or None if it isn't stored here."""
    svg = local_svg(icon_id)
    if not svg or px < 4:
        return None
    try:
        return _raster(icon_id, int(px), svg)
    except Exception:  # noqa: BLE001 - a broken SVG shouldn't stop the label
        return None


def thumb(icon_id: str, svg: str, px: int):
    try:
        return _raster(icon_id, int(px), svg)
    except Exception:  # noqa: BLE001
        return None


# --- the library -------------------------------------------------------------

def library() -> list[str]:
    """Saved icons, most recently used first."""
    found: dict[str, float] = {}
    for d in (BOOT_LIBRARY, LIBRARY):
        try:
            for p in d.glob("*.svg"):
                i = _id_from(p)
                if valid(i):
                    found[i] = max(found.get(i, 0), p.stat().st_mtime)
        except OSError:
            continue
    return sorted(found, key=found.get, reverse=True)


def is_saved(icon_id: str) -> bool:
    return any((d / _fname(icon_id)).exists() for d in (LIBRARY, BOOT_LIBRARY))


def save(icon_id: str):
    """Keep this icon (and mark it most recently used)."""
    svg = get_svg(icon_id)
    _write(LIBRARY / _fname(icon_id), svg)
    _helper("save", icon_id, svg)


def forget(icon_id: str):
    if not valid(icon_id):
        return
    try:
        (LIBRARY / _fname(icon_id)).unlink()
    except OSError:
        pass
    _helper("remove", icon_id)


def _helper(action: str, icon_id: str, svg: str | None = None):
    """With power-off protection on, the boot partition is the only place that
    survives a restart; a small root helper writes there (see protect.sh)."""
    if not os.path.exists(HELPER):
        return
    try:
        subprocess.run(["sudo", "-n", HELPER, action, _fname(icon_id)[:-4]],
                       input=(svg or "").encode(), timeout=10, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def _write(path: Path, text: str):
    with _lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(text)
            os.replace(tmp, path)
        except OSError:
            pass
