#!/usr/bin/env python3
"""
consolidate.py — Merge latest CSV files from goods_tools/ into a single GeoJSON.

Finds the latest CSV for each of redtable, ydp, and benepia patterns,
geocodes missing coordinates via Nominatim (no API key needed), and
outputs a unified GeoJSON FeatureCollection ready for a web frontend.

Usage:
    python3 scripts/consolidate.py
"""

import os
import glob
import json
import sys
import time
import re

import pandas as pd
from geopy.geocoders import Photon
from geopy.extra.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GOODS_TOOLS_DIR = "/Users/sysilion/goods_tools"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # project root
OUTPUT_FILE = os.path.join(PROJECT_DIR, "data", "map_data.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, ".geocode_cache.json")

# Each entry: (glob_pattern, source_label, has_latlon_in_csv)
CSV_PATTERNS = [
    ("must_eat_data_*.csv", "redtable", True),   # redtable.py already has Lat/Lon
    ("ydp_store_data_*.csv", "ydp", False),       # ydp.py — no coordinates
    ("store_data_*.csv", "benepia", False),       # benepia.py — no coordinates
]

GEOCODE_DELAY_S = 1.0  # seconds between geocoding requests
GEOCODE_TIMEOUT_S = 10  # per-request timeout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_latest_csv(pattern: str) -> str | None:
    """Return the most-recently-modified CSV under `pattern`."""
    files = glob.glob(os.path.join(GOODS_TOOLS_DIR, pattern))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def load_and_normalize(filepath: str, source: str) -> pd.DataFrame:
    """
    Read a CSV and normalise to columns:
        title, address, phone, category, link, lat, lon, source
    """
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    # Case-insensitive column lookup (original CSV column names vary)
    cols = {c.lower(): c for c in df.columns}

    out = pd.DataFrame()
    out["title"] = df.get(cols.get("title"), "")
    out["address"] = df.get(cols.get("address"), "")
    out["phone"] = df.get(cols.get("phone"), "")
    out["category"] = df.get(cols.get("category"), "")
    out["link"] = df.get(cols.get("link"), "")

    # Coordinates — only present in redtable CSVs
    lat_col = cols.get("latitude")
    lon_col = cols.get("longitude")
    if lat_col and lon_col:
        out["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
        out["lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    else:
        out["lat"] = pd.NA
        out["lon"] = pd.NA

    out["source"] = source
    return out


def _init_geocoder():
    """Build a rate-limited Photon geocoder (shared across calls).

    Photon (photon.komoot.io) is based on OSM data, free, no API key
    needed, and has significantly better Korean address coverage than
    Nominatim.
    """
    geolocator = Photon(timeout=GEOCODE_TIMEOUT_S)
    return RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODE_DELAY_S)


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _clean_address(raw: str) -> list[str]:
    """Normalise a Korean address and return variants to try.

    Strips phone numbers, trailing punctuation, building/floors, and
    returns progressively shorter variants so the geocoder has the best
    chance of matching.
    """
    addr = raw.strip()

    # Remove phone numbers like 010-1234-5678, 02-123-4567, 0507-1234-5678
    addr = re.sub(r'\b\d{2,4}-\d{3,4}-\d{4}\b', '', addr)
    # Remove bare phone-like numbers at end
    addr = re.sub(r'\b\d{9,12}\b', '', addr)
    # Remove trailing comma/spaces with phone leftovers
    addr = re.sub(r'[,.\s]*\d{9,}$', '', addr)
    # Clean up multiple spaces, trailing commas, punctuation
    addr = re.sub(r'[,\s]+', ' ', addr).strip()
    addr = re.sub(r'\s+$', '', addr)

    if not addr:
        return []

    # Build variants: full address, then address up to first comma,
    # then address up to last comma if different
    variants = [f"{addr}, South Korea"]
    if ',' in addr:
        first_part = addr.split(',')[0].strip()
        if first_part != addr:
            variants.append(f"{first_part}, South Korea")

    return variants


def geocode_missing(df: pd.DataFrame, geocode, cache: dict) -> pd.DataFrame:
    """Geocode rows that lack valid lat/lon, using cache + Photon."""
    missing = df[df["lat"].isna() | df["lon"].isna()].index
    if missing.empty:
        return df

    n = len(missing)
    print(f"  Geocoding {n} entries (rate-limited to 1 req/s) ...")

    for i, idx in enumerate(missing, 1):
        raw_addr = str(df.at[idx, "address"] or "").strip()
        title = str(df.at[idx, "title"] or "").strip()

        if not raw_addr:
            print(f"  [{i:>3}/{n}] ⚠️  Empty address for '{title}', skipped")
            continue

        # Cache hit (use raw address as key)
        if raw_addr in cache:
            coords = cache[raw_addr]
            if coords is not None:
                df.at[idx, "lat"], df.at[idx, "lon"] = coords
            continue

        # Try progressively cleaner address variants
        variants = _clean_address(raw_addr)
        location = None
        best_query = None

        for query in variants:
            try:
                location = geocode(query)
                if location:
                    best_query = query
                    break
            except Exception:
                continue

        if location:
            df.at[idx, "lat"] = location.latitude
            df.at[idx, "lon"] = location.longitude
            cache[raw_addr] = [location.latitude, location.longitude]
            print(f"  [{i:>3}/{n}] ✅ {raw_addr[:40]:40s} → ({location.latitude:.5f}, {location.longitude:.5f})")
        else:
            cache[raw_addr] = None
            print(f"  [{i:>3}/{n}] ❌ Not found: {raw_addr[:50]}")

        # Persist cache periodically
        if i % 50 == 0:
            _save_cache(cache)

    return df


def to_geojson(df: pd.DataFrame) -> dict:
    """Build a GeoJSON FeatureCollection. Skips rows without coordinates."""
    features = []
    for _, row in df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["lon"]), float(row["lat"])],
            },
            "properties": {
                "title": str(row["title"] or ""),
                "address": str(row["address"] or ""),
                "phone": str(row["phone"] or ""),
                "category": str(row["category"] or ""),
                "link": str(row["link"] or ""),
                "source": str(row["source"]),
            },
        })

    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  Redtable Map Data Consolidator")
    print("=" * 60)

    cache = _load_cache()
    print(f"\n📦 Geocode cache: {len(cache)} entries")

    geocode = _init_geocoder()
    source_dfs = []

    for pattern, label, has_coords in CSV_PATTERNS:
        print(f"\n🔍 [{label}] searching …")
        path = find_latest_csv(pattern)
        if not path:
            print(f"  ⚠️  No files matched '{pattern}'")
            continue

        print(f"  File: {os.path.basename(path)}")
        df = load_and_normalize(path, label)
        print(f"  Rows: {len(df)}")

        if not has_coords:
            df = geocode_missing(df, geocode, cache)

        source_dfs.append(df)

    if not source_dfs:
        print("\n❌ No data loaded. Exiting.")
        sys.exit(1)

    # Combine all data
    combined = pd.concat(source_dfs, ignore_index=True)
    
    # Deduplicate by title and address
    combined = combined.groupby(['title', 'address']).agg({
        'phone': 'first',
        'category': 'first',
        'link': lambda x: '|'.join(set(str(l) for l in x if pd.notna(l))),
        'lat': 'first',
        'lon': 'first',
        'source': lambda x: '|'.join(set(str(s) for s in x))
    }).reset_index()
    
    print(f"\n📊 Combined (deduplicated): {len(combined)} entries | "
          f"With coordinates: {combined['lat'].notna().sum()}")

    geojson = to_geojson(combined)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Written → {OUTPUT_FILE}")
    print(f"   GeoJSON features: {len(geojson['features'])}")

    _save_cache(cache)
    print(f"   Cache saved: {len(cache)} entries")
    print("\n✨ Done!")


if __name__ == "__main__":
    main()
