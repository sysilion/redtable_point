#!/usr/bin/env python3
"""
consolidate.py — Merge latest CSV files from goods_tools/ into a single GeoJSON.

Finds the latest CSV for each of redtable, ydp, and benepia patterns,
geocodes missing coordinates via Photon (no API key needed), and
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
import math
import unicodedata
from datetime import datetime

import pandas as pd
from geopy.geocoders import Photon
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# Load configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "GOODS_TOOLS_DIR": "/Users/sysilion/goods_tools",
        "CSV_PATTERNS": [
            ["must_eat_data_*.csv", "redtable", True],
            ["ydp_store_data_*.csv", "ydp", False],
            ["store_data_*.csv", "benepia", False],
        ],
        "GEOCODE_DELAY_S": 1.0,
        "GEOCODE_TIMEOUT_S": 10
    }

CONFIG = load_config()
GOODS_TOOLS_DIR = os.environ.get("GOODS_TOOLS_DIR", CONFIG["GOODS_TOOLS_DIR"])
CSV_PATTERNS = CONFIG["CSV_PATTERNS"]
GEOCODE_DELAY_S = CONFIG["GEOCODE_DELAY_S"]
GEOCODE_TIMEOUT_S = CONFIG["GEOCODE_TIMEOUT_S"]

OUTPUT_FILE = os.path.join(PROJECT_DIR, "data", "map_data.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, ".geocode_cache.json")

def find_latest_csv(pattern: str) -> str | None:
    """Return the most-recently-modified CSV under `pattern`."""
    files = glob.glob(os.path.join(GOODS_TOOLS_DIR, pattern))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def load_and_normalize(filepath: str, source: str) -> pd.DataFrame:
    """Read a CSV and normalise columns."""
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    cols = {c.lower(): c for c in df.columns}
    
    out = pd.DataFrame()
    out["title"] = df.get(cols.get("title"), "")
    out["address"] = df.get(cols.get("address"), "")
    out["phone"] = df.get(cols.get("phone"), "")
    out["category"] = df.get(cols.get("category"), "")
    out["link"] = df.get(cols.get("link"), "")
    
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

def normalize_text(text):
    text = str(text)
    # Normalize unicode
    text = unicodedata.normalize('NFKC', text)
    # Remove parentheses and contents
    text = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', text)
    text = re.sub(r'(마포점|본점|강남점|홍대점|종로점|분점)$', '', text)
    # Remove non-alphanumeric
    text = re.sub(r'[^a-zA-Z0-9가-힣]', '', text)
    return text.lower()

def _clean_address(raw: str) -> list[str]:
    addr = raw.strip()
    addr = re.sub(r'\b\d{2,4}-\d{3,4}-\d{4}\b', '', addr)
    addr = re.sub(r'\b\d{9,12}\b', '', addr)
    # Remove trailing comma/spaces with phone leftovers
    addr = re.sub(r'[,.\s]*\d{9,}$', '', addr)
    # Clean up multiple spaces, trailing commas, punctuation
    addr = re.sub(r'[,\s]+', ' ', addr).strip()
    addr = re.sub(r'\s+$', '', addr)


    if not addr: return []
    variants = [f"{addr}, South Korea"]
    if ',' in addr:
        first_part = addr.split(',')[0].strip()
        if first_part != addr:
            variants.append(f"{first_part}, South Korea")
    return variants

def geocode_missing(df: pd.DataFrame, geocode, cache: dict) -> pd.DataFrame:
    missing = df[df["lat"].isna() | df["lon"].isna()].index
    if missing.empty: return df
    
    n = len(missing)
    print(f"  Geocoding {n} entries ...")
    for i, idx in enumerate(missing, 1):
        raw_addr = str(df.at[idx, "address"] or "").strip()
        if not raw_addr: continue
        
        if raw_addr in cache:
            if cache[raw_addr]:
                df.at[idx, "lat"] = cache[raw_addr][0]
                df.at[idx, "lon"] = cache[raw_addr][1]
            continue
            
        variants = _clean_address(raw_addr)
        location = None
        for query in variants:
            try:
                location = geocode(query)
                if location: break
            except Exception: continue
        if location:
            df.at[idx, "lat"] = location.latitude
            df.at[idx, "lon"] = location.longitude
            cache[raw_addr] = [location.latitude, location.longitude]
        else:
            cache[raw_addr] = None
    return df

def to_geojson(df: pd.DataFrame) -> dict:
    features = []
    for _, row in df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]): continue
        features.append({
            "type": "Feature",
            "geometry": { "type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])] },
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

def consolidate_group(group):
    # 가장 긴 주소를 대표 주소로 선택
    longest_address = group.loc[group['address'].astype(str).str.len().idxmax(), 'address']
    
    # lat/lon이 존재하는 행을 우선 선택
    valid_lat = group['lat'].dropna()
    valid_lon = group['lon'].dropna()
    lat = valid_lat.iloc[0] if not valid_lat.empty else pd.NA
    lon = valid_lon.iloc[0] if not valid_lon.empty else pd.NA

    items = []
    for _, row in group.iterrows():
        if pd.notna(row['link']):
            items.append({'link': str(row['link']), 'source': str(row['source'])})
    unique_items = []
    seen = set()
    for item in items:
        key = (item['link'], item['source'])
        if key not in seen:
            unique_items.append(item)
            seen.add(key)
    
    return pd.Series({
        'title': group['title'].iloc[0],
        'address': longest_address,
        'phone': group['phone'].iloc[0],
        'category': group['category'].iloc[0],
        'link': json.dumps(unique_items),
        'lat': lat,
        'lon': lon,
        'source': 'combined'
    })

def main():
    print("=" * 60)
    print("  Redtable Map Data Consolidator")
    print("=" * 60)
    
    cache = _load_cache()
    geocode = _init_geocoder()
    source_dfs = []

    for pattern, label, has_coords in CSV_PATTERNS:
        path = find_latest_csv(pattern)
        if not path: continue
        df = load_and_normalize(path, label)
        if not has_coords: df = geocode_missing(df, geocode, cache)
        source_dfs.append(df)
    
    combined = pd.concat(source_dfs, ignore_index=True)
    
    # 1. 주소 정제: 층/동/호수/지하 정보 제거
    def get_base_address(addr):
        addr = str(addr)
        addr = re.sub(r'\s*(지하\s*[\d,/-]+층|[\d,/-]+층|B\d+|[0-9]+동|[0-9]+호|[0-9]+-[0-9]+호)\b', '', addr)
        return re.sub(r'\s+', '', addr).lower()

    # 2. 매장 이름 정규화
    combined['clean_title'] = combined['title'].apply(normalize_text)
    combined['base_address'] = combined['address'].apply(get_base_address)

    def consolidate_group(group):
        # 우선순위: Redtable 주소를 최우선으로 선택, 없으면 가장 긴 주소 선택
        redtable_row = group[group['source'] == 'redtable']
        if not redtable_row.empty:
            address = redtable_row['address'].iloc[0]
        else:
            address = group.loc[group['address'].astype(str).str.len().idxmax(), 'address']
        
        # lat/lon이 존재하는 행을 우선 선택
        valid_lat = group['lat'].dropna()
        valid_lon = group['lon'].dropna()
        lat = valid_lat.iloc[0] if not valid_lat.empty else pd.NA
        lon = valid_lon.iloc[0] if not valid_lon.empty else pd.NA

        items = []
        found_redtable = False
        extracted_id = None
        
        # 1. 수집된 링크 파싱 및 ID 추출
        for _, row in group.iterrows():
            if pd.isna(row['link']): continue
            
            link_val = str(row['link'])
            try:
                links = json.loads(link_val)
            except json.JSONDecodeError:
                links = [{'link': link_val, 'source': str(row['source'])}]
            
            for item in links:
                items.append(item)
                # ID 추출 (Redtable/YDP/Benepia 링크에서)
                match = re.search(r'/(?:food|store)/(\d+)', item['link'])
                if match and not extracted_id:
                    extracted_id = match.group(1)

        # 2. 모든 소스에 대해 링크 존재 확인 및 복원
        if extracted_id:
            all_sources = {
                'redtable': f'https://redtable.global/ko/food/{extracted_id}',
                'ydp': f'https://ydp.redtable.global/store/{extracted_id}',
                'benepia': f'https://benepia.redtable.global/store/{extracted_id}'
            }
            
            for source, url in all_sources.items():
                # 이미 존재하는 링크인지 확인
                exists = any(item['link'] == url for item in items)
                if not exists:
                    items.append({
                        'link': url,
                        'source': source
                    })

        unique_items = []
        seen = set()
        for item in items:
            key = (item['link'], item['source'])
            if key not in seen:
                unique_items.append(item)
                seen.add(key)
        
        return pd.Series({
            'title': group['title'].iloc[0],
            'address': address,
            'phone': group['phone'].iloc[0],
            'category': group['category'].iloc[0],
            'link': json.dumps(unique_items),
            'lat': lat,
            'lon': lon,
            'source': 'combined'
        })

    combined = combined.groupby(['clean_title', 'base_address'], group_keys=False).apply(consolidate_group, include_groups=False).reset_index(drop=True)

    # Jitter
    coord_counts = combined.groupby(['lat', 'lon']).size()
    for (lat, lon), count in coord_counts.items():
        if count > 1 and pd.notna(lat) and pd.notna(lon):
            mask = (combined['lat'] == lat) & (combined['lon'] == lon)
            indices = combined[mask].index
            for idx, row_idx in enumerate(indices):
                angle = (idx / count) * 2 * math.pi
                combined.at[row_idx, 'lat'] += math.cos(angle) * 0.00005
                combined.at[row_idx, 'lon'] += math.sin(angle) * 0.00005
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(to_geojson(combined), f, ensure_ascii=False, indent=2)
    _save_cache(cache)
    print("✨ Done!")

if __name__ == "__main__":
    main()
