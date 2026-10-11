#!/usr/bin/env python3
"""
Cloud catalog scan entrypoint for GitHub Actions.

- Collects local-coop titles (demo source + optional free RAWG if key present)
- Tags Xbox Game Pass (All-Inclusive) vs GeForce NOW (BYOG)
- Upserts into Supabase with screenshots as jsonb arrays (no HTTP 400)

Budget: 0€ — uses only free tiers / public endpoints.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import requests

from agent import SupabaseGamesClient, configure_logging, normalize_game_payload

log = logging.getLogger("run_cloud_scan")

G2A_REF = "reflink-07f53ba10b"

# Seed catalog — free, offline-capable for Actions without external paid APIs.
SEED_CATALOG: List[Dict[str, Any]] = [
    {
        "title": "It Takes Two",
        "max_players": 2,
        "genres": ["Co-op", "Adventure"],
        "platforms": ["PC", "Xbox", "PlayStation"],
        "screenshots": [
            "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=800&q=80",
            "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=800&q=80",
        ],
        "cover": "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=600&q=80",
        "gfn_status": "BYOG",
        "game_pass_status": "All-Inclusive",
        "buyer_type": "cd_key",
        "cpu": "Intel i5-8400 / Ryzen 5 1600",
        "gpu": "GTX 1060 / RX 580",
        "ram_gb": 8,
        "storage_gb": 50,
        "store_links": {
            "steam": "https://store.steampowered.com/app/1426210/",
            "xbox": "https://www.xbox.com/",
            "g2a": f"https://www.g2a.com/?gtag={G2A_REF}",
        },
    },
    {
        "title": "Moving Out 2",
        "max_players": 4,
        "genres": ["Party", "Physics"],
        "platforms": ["PC", "Xbox", "Nintendo"],
        "screenshots": [
            "https://images.unsplash.com/photo-1493711662062-fa541adb3fc8?w=800&q=80",
            "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=800&q=80",
        ],
        "gfn_status": "BYOG",
        "game_pass_status": "All-Inclusive",
        "buyer_type": "cd_key",
        "cpu": "Intel i5-2500K",
        "gpu": "GTX 760",
        "ram_gb": 8,
        "storage_gb": 10,
        "store_links": {
            "steam": "https://store.steampowered.com/",
            "g2a": f"https://www.g2a.com/?gtag={G2A_REF}",
        },
    },
    {
        "title": "Overcooked! 2",
        "max_players": 4,
        "genres": ["Party", "Cooking"],
        "platforms": ["PC", "Xbox", "PlayStation", "Nintendo"],
        "screenshots": [
            "https://images.unsplash.com/photo-1612287230202-1ff1d85d1bdf?w=800&q=80",
        ],
        "gfn_status": "BYOG",
        "game_pass_status": "Not listed",
        "buyer_type": "cd_key",
        "cpu": "Core 2 Duo E8400",
        "gpu": "GTX 660",
        "ram_gb": 4,
        "storage_gb": 3,
        "store_links": {"g2a": f"https://www.g2a.com/?gtag={G2A_REF}"},
    },
    {
        "title": "Pummel Party",
        "max_players": 8,
        "genres": ["Party", "Minigames"],
        "platforms": ["PC"],
        "screenshots": [
            "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=800&q=80",
            "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=800&q=80",
            "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=800&q=80",
        ],
        "gfn_status": "BYOG",
        "game_pass_status": "Not listed",
        "buyer_type": "cd_key",
        "cpu": "i5-2400",
        "gpu": "GTX 650",
        "ram_gb": 4,
        "storage_gb": 4,
        "store_links": {"g2a": f"https://www.g2a.com/?gtag={G2A_REF}"},
    },
    {
        "title": "Gang Beasts",
        "max_players": 8,
        "genres": ["Party", "Fighting"],
        "platforms": ["PC", "Xbox", "PlayStation"],
        "screenshots": [
            "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=800&q=80",
        ],
        "gfn_status": "BYOG",
        "game_pass_status": "All-Inclusive",
        "buyer_type": "cd_key",
        "cpu": "i5-2400",
        "gpu": "GTX 550 Ti",
        "ram_gb": 4,
        "storage_gb": 2,
        "store_links": {"g2a": f"https://www.g2a.com/?gtag={G2A_REF}"},
    },
]


def enrich_cloud_transparency(row: Dict[str, Any]) -> Dict[str, Any]:
    """Force explicit GP All-Inclusive vs GFN BYOG wording in status fields."""
    gfn = (row.get("gfn_status") or "").strip()
    gp = (row.get("game_pass_status") or "").strip()
    if gfn and "BYOG" not in gfn.upper() and gfn.lower() not in {"unavailable", "not supported"}:
        # Keep short badge value; documentation lives in UI/copy
        if gfn.upper() in {"YES", "SUPPORTED", "AVAILABLE"}:
            row["gfn_status"] = "BYOG"
    if gp and gp.lower() in {"yes", "included", "available"}:
        row["game_pass_status"] = "All-Inclusive"
    # Never mark secondary accounts as CD-Key
    if row.get("buyer_type") == "secondary_account":
        links = row.get("store_links") or {}
        if isinstance(links, dict):
            links = {**links, "warning": "secondary_account_not_cd_key"}
            row["store_links"] = links
    return row


def fetch_rawg_optional(api_key: str, query: str = "party") -> List[Dict[str, Any]]:
    """Optional free-tier RAWG enrichment. Fail soft — never crash the workflow."""
    try:
        url = "https://api.rawg.io/api/games"
        res = requests.get(
            url,
            params={"key": api_key, "search": query, "page_size": 5},
            timeout=30,
        )
        if res.status_code >= 400:
            log.warning("RAWG skipped (%s): %s", res.status_code, res.text[:200])
            return []
        results = res.json().get("results") or []
        out: List[Dict[str, Any]] = []
        for item in results:
            short = item.get("short_screenshots") or []
            shots = [s.get("image") for s in short if isinstance(s, dict) and s.get("image")]
            out.append(
                {
                    "title": item.get("name") or "RAWG title",
                    "max_players": 4,
                    "genres": [g.get("name") for g in (item.get("genres") or []) if g.get("name")],
                    "platforms": [
                        p.get("platform", {}).get("name")
                        for p in (item.get("platforms") or [])
                        if p.get("platform")
                    ],
                    "screenshots": shots,  # list → jsonb
                    "cover": (item.get("background_image") or (shots[0] if shots else None)),
                    "gfn_status": "BYOG",
                    "game_pass_status": "Unknown",
                    "buyer_type": "cd_key",
                    "cpu": None,
                    "gpu": None,
                    "ram_gb": None,
                    "storage_gb": None,
                    "store_links": {"g2a": f"https://www.g2a.com/?gtag={G2A_REF}"},
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001 — Actions must not fail hard on optional API
        log.warning("RAWG optional fetch failed: %s", exc)
        return []


def collect_catalog(include_rawg: bool = True) -> List[Dict[str, Any]]:
    rows = [enrich_cloud_transparency(dict(r)) for r in SEED_CATALOG]
    rawg_key = os.environ.get("RAWG_API_KEY", "").strip()
    if include_rawg and rawg_key:
        extra = fetch_rawg_optional(rawg_key)
        rows.extend(enrich_cloud_transparency(r) for r in extra)
    # Pre-normalize so dry-run JSON matches what Supabase receives
    return [normalize_game_payload(r) for r in rows]


def run(dry_run: bool = False, include_rawg: bool = True) -> int:
    catalog = collect_catalog(include_rawg=include_rawg)
    log.info("Collected %s normalized game row(s)", len(catalog))

    # Integrity: screenshots must be lists (jsonb), never strings
    for row in catalog:
        if not isinstance(row.get("screenshots"), list):
            raise TypeError(f"screenshots must be list/jsonb for slug={row.get('slug')}")
        if row.get("screenshots") is None:
            raise TypeError("screenshots must not be null — use []")

    if dry_run:
        print(json.dumps(catalog, indent=2))
        log.info("Dry-run complete — no Supabase write.")
        return 0

    client = SupabaseGamesClient()
    client.upsert_games(catalog)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan cloud/party catalog → Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print payload, skip upsert")
    parser.add_argument("--no-rawg", action="store_true", help="Skip optional RAWG enrichment")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)
    try:
        return run(dry_run=args.dry_run, include_rawg=not args.no_rawg)
    except Exception as exc:  # noqa: BLE001
        log.error("Scan failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
