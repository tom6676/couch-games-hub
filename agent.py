"""
Party Cloud Board — Supabase upsert agent.

Ensures screenshots are always a JSON-serializable list (jsonb-safe) and
technical columns are coerced to avoid PostgREST HTTP 400 errors.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

import requests

log = logging.getLogger("party_cloud_agent")

# Columns expected by the `games` table (free-tier Supabase).
TECH_COLUMNS = (
    "title",
    "slug",
    "max_players",
    "genres",
    "platforms",
    "screenshots",
    "cover",
    "gfn_status",
    "game_pass_status",
    "buyer_type",
    "cpu",
    "gpu",
    "ram_gb",
    "storage_gb",
    "store_links",
)


def _as_list(value: Any) -> List[Any]:
    """Coerce to a list suitable for jsonb / text[] columns."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None and v != ""]
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [v for v in parsed if v is not None and v != ""]
            except json.JSONDecodeError:
                pass
        # comma-separated fallback
        return [p.strip() for p in text.split(",") if p.strip()]
    return [value]


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_str(value: Any, default: Optional[str] = None) -> Optional[str]:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_object(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def normalize_game_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a PostgREST-safe row.

    Critical for avoiding 400:
    - screenshots → always a JSON array (never a bare string)
    - genres / platforms → arrays
    - store_links → object (jsonb)
    - numeric fields → int or null
    - buyer_type → constrained enum-like string
    """
    buyer = (_as_str(raw.get("buyer_type"), "unknown") or "unknown").lower()
    if buyer not in {"cd_key", "secondary_account", "unknown"}:
        buyer = "unknown"

    screenshots = _as_list(raw.get("screenshots"))
    # Ensure every screenshot entry is a string URL
    screenshots = [str(u).strip() for u in screenshots if str(u).strip()]

    payload: Dict[str, Any] = {
        "title": _as_str(raw.get("title"), "Untitled") or "Untitled",
        "slug": _as_str(raw.get("slug"))
        or _slugify(_as_str(raw.get("title"), "untitled") or "untitled"),
        "max_players": _as_int(raw.get("max_players")) or 0,
        "genres": _as_list(raw.get("genres")),
        "platforms": _as_list(raw.get("platforms")),
        "screenshots": screenshots,  # jsonb array — never null, never a string
        "cover": _as_str(raw.get("cover")) or (screenshots[0] if screenshots else None),
        "gfn_status": _as_str(raw.get("gfn_status"), "Unknown"),
        "game_pass_status": _as_str(raw.get("game_pass_status"), "Unknown"),
        "buyer_type": buyer,
        "cpu": _as_str(raw.get("cpu")),
        "gpu": _as_str(raw.get("gpu")),
        "ram_gb": _as_int(raw.get("ram_gb")),
        "storage_gb": _as_int(raw.get("storage_gb")),
        "store_links": _as_object(raw.get("store_links")),
    }
    return payload


def _slugify(title: str) -> str:
    out = []
    for ch in title.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_"}:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "game"


class SupabaseGamesClient:
    """Minimal REST client — no paid SDKs required."""

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        table: str = "games",
    ) -> None:
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
            "SUPABASE_ANON_KEY", ""
        )
        self.table = table
        if not self.url or not self.key:
            raise RuntimeError(
                "Missing SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)."
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    def upsert_games(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [normalize_game_payload(r) for r in rows]
        if not payload:
            log.info("No rows to upsert.")
            return []

        endpoint = f"{self.url}/rest/v1/{self.table}?on_conflict=slug"
        # Explicit Prefer for upsert on unique slug
        headers = self._headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"

        log.info("Upserting %s game(s) → %s", len(payload), self.table)
        # Log a compact sample to debug 400s without dumping secrets
        sample = {k: payload[0].get(k) for k in ("slug", "screenshots", "ram_gb", "buyer_type")}
        log.debug("Sample payload types: %s", {k: type(v).__name__ for k, v in sample.items()})

        res = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=60)
        if res.status_code >= 400:
            # Surface PostgREST body — typical 400 = wrong jsonb / column type
            log.error("Supabase %s: %s", res.status_code, res.text[:2000])
            raise RuntimeError(f"Supabase upsert failed ({res.status_code}): {res.text[:500]}")

        data = res.json() if res.text else []
        log.info("Upsert OK — %s row(s) returned", len(data) if isinstance(data, list) else 1)
        return data if isinstance(data, list) else [data]


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    configure_logging(verbose="--verbose" in sys.argv)
    demo = [
        {
            "title": "Smoke Test Party Title",
            "max_players": 4,
            "genres": ["Party"],
            "platforms": ["PC"],
            "screenshots": [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ],
            "gfn_status": "BYOG",
            "game_pass_status": "All-Inclusive",
            "buyer_type": "cd_key",
            "cpu": "i5",
            "gpu": "GTX 1060",
            "ram_gb": 8,
            "storage_gb": 20,
            "store_links": {"g2a": "https://www.g2a.com/"},
        }
    ]
    print(json.dumps(normalize_game_payload(demo[0]), indent=2))
