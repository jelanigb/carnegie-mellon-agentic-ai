"""Lightweight client for the HUD Fair Market Rents (FMR) API.

Docs: https://www.huduser.gov/portal/dataset/fmr-api.html
Design notes: docs/implementation_plan.md §2 (HUD FMR API: Implementation Notes)
and §9 (this client's build plan).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://www.huduser.gov/hudapi/public"

_REPO_ROOT = Path(__file__).resolve().parents[2]

# TODO(security): decide whether to drop the on-disk token fallback and require
# HUD_FMR_TOKEN. The file itself is gitignored and holds no secret in this repo, but
# naming the path in a public source file advertises where a credential is kept.
# Env-var-only is stricter; the file fallback is more convenient for local runs.
# Same question applies to tools/llm_client.py. Owner's call — not changed unilaterally
# because it would break a working auth path.
_TOKEN_FILE = _REPO_ROOT / "ignore" / "fmr_key"

# TODO(U2): _DiskCache is not concurrency-safe — set() rewrites the entire JSON file,
# so two processes sharing this cache can clobber each other's writes. It went unnoticed
# until two agents hit the HUD API in parallel during U1 (worked around there by passing
# a separate cache_path). Fix with atomic write-and-rename plus a lock file, or accept
# the limitation and document that concurrent callers must pass distinct cache paths.
_CACHE_FILE = _REPO_ROOT / "data" / "raw" / "hud_fmr_cache.json"

# HUD's cap is 60 requests/minute; 1 call/second stays comfortably under it.
_MIN_SECONDS_BETWEEN_CALLS = 1.0

_BEDROOM_FIELDS = {
    0: "Efficiency",
    1: "One-Bedroom",
    2: "Two-Bedroom",
    3: "Three-Bedroom",
    4: "Four-Bedroom",
}


class HudFmrApiError(Exception):
    """Raised when the HUD FMR API returns a non-200 response, or auth is missing."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HUD FMR API error {status_code}: {body}")


@dataclass
class FmrResult:
    entityid: str
    year: str
    area_name: str
    is_safmr: bool
    zip_requested: Optional[str]
    used_msa_fallback: bool
    rents: dict
    raw: dict


def _load_token() -> str:
    env_token = os.environ.get("HUD_FMR_TOKEN")
    if env_token:
        return env_token.strip()
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text().strip()
    raise HudFmrApiError(
        0, f"No HUD FMR token found. Set HUD_FMR_TOKEN or create {_TOKEN_FILE}."
    )


class _DiskCache:
    def __init__(self, path: Path):
        self._path = path
        self._data: dict = {}
        if path.exists():
            self._data = json.loads(path.read_text())

    def get(self, key: str):
        return self._data.get(key)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))


class HudFmrClient:
    """Thin wrapper around the HUD FMR API: auth, local caching, client-side rate
    limiting, and normalizing the flat vs. Small Area FMR (SAFMR) response shapes
    into one consistent shape.
    """

    def __init__(self, token: Optional[str] = None, cache_path: Path = _CACHE_FILE):
        self._token = token or _load_token()
        self._session = requests.Session()
        self._cache = _DiskCache(cache_path)
        self._last_call_time = 0.0

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        cache_key = f"{path}?{json.dumps(params or {}, sort_keys=True)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        elapsed = time.monotonic() - self._last_call_time
        if elapsed < _MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(_MIN_SECONDS_BETWEEN_CALLS - elapsed)

        resp = self._session.get(
            f"{BASE_URL}/{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
            timeout=30,
        )
        self._last_call_time = time.monotonic()

        if resp.status_code != 200:
            raise HudFmrApiError(resp.status_code, resp.text)

        result = resp.json()
        self._cache.set(cache_key, result)
        return result

    def list_states(self) -> list:
        """GET /fmr/listStates -> [{state_name, state_code, state_num, category}, ...]"""
        return self._get("fmr/listStates")

    def list_counties(self, state_code: str) -> list:
        """GET /fmr/listCounties/{state_code} ->
        [{state_code, fips_code, county_name, town_name, category}, ...]
        `fips_code` is the 10-digit entityid used by get_fmr().
        """
        return self._get(f"fmr/listCounties/{state_code}")

    def get_fmr(
        self,
        entityid: str,
        year: Optional[int] = None,
        zip_code: Optional[str] = None,
    ) -> FmrResult:
        """GET /fmr/data/{entityid}[?year=year].

        `zip_code` defaults to None, so the result is metro-level by default: for an
        ordinary county there's only one metro-wide record anyway, and for a Small
        Area FMR (SAFMR) county the code falls back to the "MSA level" entry unless
        a specific zip_code is passed and matches. This matches the Kaggle/Redfin
        data, which are both metro-level (see docs/implementation_plan.md §2, §9).
        """
        params = {"year": year} if year is not None else None
        payload = self._get(f"fmr/data/{entityid}", params=params)
        data = payload["data"]
        basicdata = data["basicdata"]

        if isinstance(basicdata, list):
            # SAFMR shape: ZIP-keyed entries + one "MSA level" entry; year lives at
            # the top level of `data`, not inside each entry.
            is_safmr = True
            resolved_year = data.get("year")
            entry = None
            if zip_code is not None:
                entry = next(
                    (e for e in basicdata if e.get("zip_code") == zip_code), None
                )
            used_msa_fallback = entry is None
            if entry is None:
                entry = next(e for e in basicdata if e.get("zip_code") == "MSA level")
            rents = {k: v for k, v in entry.items() if k != "zip_code"}
        else:
            # Ordinary shape: one flat record; year lives inside basicdata.
            is_safmr = False
            used_msa_fallback = False
            resolved_year = basicdata.get("year")
            rents = {k: v for k, v in basicdata.items() if k != "year"}
            entry = basicdata

        return FmrResult(
            entityid=entityid,
            year=resolved_year,
            area_name=data.get("area_name", ""),
            is_safmr=is_safmr,
            zip_requested=zip_code,
            used_msa_fallback=used_msa_fallback,
            rents=rents,
            raw=entry,
        )

    def get_fmr_for_bedroom(
        self,
        entityid: str,
        bedrooms: int,
        year: Optional[int] = None,
        zip_code: Optional[str] = None,
    ) -> dict:
        """Single rent figure for a given bedroom count. Caps at Four-Bedroom
        (HUD publishes no field beyond it) instead of raising.
        """
        bedroom_cap_exceeded = bedrooms > 4
        bedrooms_used = min(bedrooms, 4)
        result = self.get_fmr(entityid, year=year, zip_code=zip_code)
        field_name = _BEDROOM_FIELDS[bedrooms_used]
        return {
            "rent": result.rents[field_name],
            "bedrooms_requested": bedrooms,
            "bedrooms_used": bedrooms_used,
            "bedroom_cap_exceeded": bedroom_cap_exceeded,
            "year": result.year,
            "is_safmr": result.is_safmr,
            "used_msa_fallback": result.used_msa_fallback,
        }
