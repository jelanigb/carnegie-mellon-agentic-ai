"""Lightweight client for the HUD Fair Market Rents (FMR) API.

Docs: https://www.huduser.gov/portal/dataset/fmr-api.html
Design notes: docs/implementation_plan.md §2 (HUD FMR API: Implementation Notes)
and §9 (this client's build plan).
"""

from __future__ import annotations

import json
import os
import tempfile
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
_TOKEN_FILE = _REPO_ROOT / "ignore" / "fmr_key.txt"

# Resolved in U2: writes are now atomic (write-to-temp then rename), and the residual
# concurrency limitation is documented on _DiskCache rather than left as a TODO.
# Concurrent callers must still pass distinct cache_path values.
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


def bedroom_field(bedrooms: int) -> tuple[str, bool]:
    """Map a bedroom count to its HUD rent field, and report whether it was capped.

    HUD publishes no field beyond Four-Bedroom, so a 5+ bedroom unit is priced against
    the four-bedroom figure. That is an approximation and the caller is expected to
    disclose it (`FlagKind.FMR_BEDROOM_CAP_EXCEEDED`), which is why the cap is returned
    alongside the field rather than applied silently.

    Public as of U5. The rent regression normalizes thousands of rows against FMR and
    needs the mapping without paying for a client call per row, but the capping rule
    must not be reimplemented at the call site — two copies would drift, and a training
    set capped differently from the inference path is a silent model defect.
    """
    capped = bedrooms > 4
    return _BEDROOM_FIELDS[min(max(bedrooms, 0), 4)], capped


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
    """Whole-file JSON cache with atomic writes.

    Resolved in U2 (the TODO above): `set()` still serializes the entire dictionary,
    but it now writes to a temporary file in the same directory and `os.replace`s it
    over the target. On POSIX that rename is atomic, so a reader — or a crash — can no
    longer catch the cache half-written, which was the failure that could destroy an
    hour of accumulated HUD pulls rather than merely lose the newest entry.

    **The concurrency limitation is accepted and documented, not fixed.** Two processes
    interleaving `set()` calls still lose one another's writes: each holds the whole
    dictionary in memory from load time and its rename replaces the other's file
    wholesale. A lock file would close that, and it is not worth the complexity here —
    the loss is a cache miss, which costs one HTTP call against a 60/minute budget, and
    the only observed case (two agents pulling in parallel during U1) is already handled
    by passing distinct `cache_path` values. Callers running concurrently should keep
    doing that.
    """

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
        # Same directory as the target, so the replace below is a rename within one
        # filesystem rather than a copy across two.
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(self._data, handle, indent=2)
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


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

    def get_fmr_zip_table(
        self, entityid: str, year: Optional[int] = None
    ) -> dict:
        """Every ZIP-level rent schedule for a Small Area FMR county, in one call.

        Returns `{zip_code: {bedroom_field: rent}}`, empty for a county HUD does not
        publish Small Area FMRs for. The "MSA level" entry is excluded — callers wanting
        the county-wide figure should use `get_fmr` without a `zip_code`, so that the
        two resolutions stay visibly distinct rather than one hiding inside the other.

        **Added for the rent model, and the reason is parsing rather than network.**
        `get_fmr(entityid, zip_code=...)` already works per ZIP, and because `zip_code`
        is applied client-side after the fetch it costs no extra HTTP request. But it
        rescans the county's full ZIP list — 474 entries for Los Angeles — once per
        lookup, and training normalizes 5,688 rows. One table per county, built once,
        is the same data at a fraction of the work.
        """
        payload = self._get(
            f"fmr/data/{entityid}", params={"year": year} if year is not None else None
        )
        basicdata = payload["data"]["basicdata"]
        if not isinstance(basicdata, list):
            return {}
        return {
            entry["zip_code"]: {k: v for k, v in entry.items() if k != "zip_code"}
            for entry in basicdata
            if entry.get("zip_code") and entry["zip_code"] != "MSA level"
        }

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
        field_name, bedroom_cap_exceeded = bedroom_field(bedrooms)
        bedrooms_used = min(max(bedrooms, 0), 4)
        result = self.get_fmr(entityid, year=year, zip_code=zip_code)
        return {
            "rent": result.rents[field_name],
            "bedrooms_requested": bedrooms,
            "bedrooms_used": bedrooms_used,
            "bedroom_cap_exceeded": bedroom_cap_exceeded,
            "year": result.year,
            "is_safmr": result.is_safmr,
            "used_msa_fallback": result.used_msa_fallback,
        }
