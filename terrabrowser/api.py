"""Fetching planet data from the NASA Exoplanet Archive TAP service, with a local cache."""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
OVERVIEW_URL = "https://exoplanetarchive.ipac.caltech.edu/overview/"

COLUMNS = [
    "pl_name", "hostname", "st_spectype", "st_teff", "st_rad", "st_mass", "st_lum",
    "sy_dist", "sy_snum", "sy_pnum",
    "pl_rade", "pl_bmasse", "pl_bmassprov", "pl_insol", "pl_eqt",
    "pl_orbper", "pl_orbsmax", "pl_orbeccen",
    "disc_year", "discoverymethod", "disc_facility", "ra", "dec",
]

# Small planets (rocky or borderline) around stars with a known temperature.
# Habitable-zone filtering happens locally so missing insolation values can be derived.
QUERY = (
    f"select {', '.join(COLUMNS)} from pscomppars "
    "where (pl_rade <= 2.5 or (pl_rade is null and pl_bmasse <= 10)) "
    "and st_teff is not null"
)

CACHE_PATH = Path.home() / ".terrabrowser" / "planets.json"
CACHE_TTL_SECONDS = 24 * 3600


def fetch_from_archive(timeout: float = 60) -> list[dict]:
    url = TAP_URL + "?" + urllib.parse.urlencode({"query": QUERY, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": "Terrabrowser/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _read_cache() -> tuple[list[dict], float] | None:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return payload["rows"], payload["fetched_at"]
    except (OSError, ValueError, KeyError):
        return None


def _write_cache(rows: list[dict]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"fetched_at": time.time(), "rows": rows}), encoding="utf-8")
    except OSError:
        pass  # caching is best-effort


def load_planets(force_refresh: bool = False) -> tuple[list[dict], str]:
    """Return (rows, source description). Uses the cache when fresh, falls back to it when offline."""
    cached = _read_cache()
    if cached and not force_refresh and time.time() - cached[1] < CACHE_TTL_SECONDS:
        return cached[0], "cache from " + time.strftime("%Y-%m-%d %H:%M", time.localtime(cached[1]))
    try:
        rows = fetch_from_archive()
    except Exception:
        if cached:
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(cached[1]))
            return cached[0], f"offline - using cache from {stamp}"
        raise
    _write_cache(rows)
    return rows, "live from NASA Exoplanet Archive"


def overview_url(planet_name: str) -> str:
    return OVERVIEW_URL + urllib.parse.quote(planet_name)
