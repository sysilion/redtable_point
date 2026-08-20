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
import re
import math
import unicodedata

import pandas as pd
from geopy.geocoders import Photon
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderQueryError, GeocoderServiceError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")

DEFAULT_CONFIG = {
    "GOODS_TOOLS_DIR": "/Users/sysilion/goods_tools",
    "CSV_PATTERNS": [
        ["must_eat_data_*.csv", "redtable", True],
        ["ydp_store_data_*.csv", "ydp", False],
        ["store_data_*.csv", "benepia", False],
    ],
    "GEOCODE_DELAY_S": 1.0,
    "GEOCODE_TIMEOUT_S": 10,
}


def load_config() -> dict:
    """Load config.json, falling back to the built-in defaults per key."""
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ! config.json 을 읽지 못해 기본값을 사용합니다: {exc}")
    return config


CONFIG = load_config()
GOODS_TOOLS_DIR = os.environ.get("GOODS_TOOLS_DIR", CONFIG["GOODS_TOOLS_DIR"])
CSV_PATTERNS = CONFIG["CSV_PATTERNS"]
GEOCODE_DELAY_S = CONFIG["GEOCODE_DELAY_S"]
GEOCODE_TIMEOUT_S = CONFIG["GEOCODE_TIMEOUT_S"]

OUTPUT_FILE = os.path.join(PROJECT_DIR, "data", "map_data.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, ".geocode_cache.json")

# 지오코딩은 건당 GEOCODE_DELAY_S 초가 걸리므로, 중간에 죽어도 작업이 날아가지
# 않도록 이 건수마다 캐시를 디스크에 내린다.
CACHE_SAVE_EVERY = 25

# 같은 좌표에 겹친 매장을 원형으로 흩뿌리는 거리(약 5m)
JITTER_DEG = 0.00005

DEFAULT_CATEGORY = "기타"

# 값이 없음을 뜻하는 문자열들. 수집기가 'N/A' 를 쓰고, pandas 가 결측치를
# str() 하면 'nan' 이 되므로 둘 다 빈 값으로 취급한다.
_EMPTY_TOKENS = {"", "nan", "none", "n/a", "na", "<na>", "null"}

TEXT_FIELDS = ("title", "address", "phone", "category", "link")


def _safe_str(value) -> str:
    """Stringify a cell, turning NaN/'nan'/'N/A' into an empty string."""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in _EMPTY_TOKENS else text


def _write_json_atomic(path: str, payload) -> None:
    """Write JSON via a temp file + rename so a crash can't truncate the target."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _filename_sort_key(path: str):
    """Sort by the YYYYMMDD stamp in the filename, then mtime as a tiebreaker.

    mtime alone is unreliable in CI: a fresh `git checkout` stamps every file
    with the same time, so the 'latest' CSV would be picked arbitrarily.
    """
    dates = re.findall(r"\d{8}", os.path.basename(path))
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return (dates[-1] if dates else "", mtime)


def find_latest_csv(pattern: str) -> str | None:
    """Return the newest CSV under `pattern`, by filename date then mtime."""
    files = glob.glob(os.path.join(GOODS_TOOLS_DIR, pattern))
    if not files:
        return None
    return max(files, key=_filename_sort_key)


def load_and_normalize(filepath: str, source: str) -> pd.DataFrame:
    """Read a CSV and normalise columns."""
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    cols = {c.lower(): c for c in df.columns}

    out = pd.DataFrame(index=df.index)
    for field in TEXT_FIELDS:
        src = cols.get(field)
        out[field] = df[src].map(_safe_str) if src else ""

    lat_col = cols.get("latitude")
    lon_col = cols.get("longitude")
    if lat_col and lon_col:
        out["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
        out["lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    else:
        out["lat"] = float("nan")
        out["lon"] = float("nan")

    out["source"] = source
    return out


def _init_geocoder():
    geolocator = Photon(timeout=GEOCODE_TIMEOUT_S)
    # swallow_exceptions 의 기본값은 True 이다. 그대로 두면 타임아웃·서비스 오류가
    # None 으로 뭉개져서 "주소를 못 찾음" 과 구분할 수 없고, 그 결과가 캐시에
    # 영구 기록된다. 오류를 그대로 올려받아 캐싱 여부를 직접 판단한다.
    return RateLimiter(
        geolocator.geocode,
        min_delay_seconds=GEOCODE_DELAY_S,
        max_retries=3,
        error_wait_seconds=5.0,
        swallow_exceptions=False,
    )


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    _write_json_atomic(CACHE_FILE, cache)


def normalize_text(text) -> str:
    text = _safe_str(text)
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Remove parentheses and contents
    text = re.sub(r"\(.*?\)|（.*?）|\[.*?\]|【.*?】", "", text)
    text = re.sub(r"(마포점|본점|강남점|홍대점|종로점|분점)$", "", text)
    # Remove non-alphanumeric
    text = re.sub(r"[^a-zA-Z0-9가-힣]", "", text)
    return text.lower()


def get_base_address(addr) -> str:
    """Strip floor/building/unit noise so the same building collapses into one key."""
    addr = _safe_str(addr)
    addr = re.sub(
        r"\s*(지하\s*[\d,/-]+층|[\d,/-]+층|B\d+|[0-9]+동|[0-9]+호|[0-9]+-[0-9]+호)\b",
        "",
        addr,
    )
    return re.sub(r"\s+", "", addr).lower()


def _clean_address(raw: str) -> list[str]:
    """Build geocoder queries for an address, widest match last."""
    addr = _safe_str(raw)
    addr = re.sub(r"\b\d{2,4}-\d{3,4}-\d{4}\b", "", addr)
    addr = re.sub(r"\b\d{9,12}\b", "", addr)
    # Remove trailing phone leftovers
    addr = re.sub(r"[,.\s]*\d{9,}$", "", addr)
    # Collapse whitespace but keep commas: they mark the detail part we may drop.
    addr = re.sub(r"[ \t]+", " ", addr).strip().strip(",").strip()
    if not addr:
        return []

    def flatten(text: str) -> str:
        return re.sub(r"[,\s]+", " ", text).strip()

    full = flatten(addr)
    variants = [f"{full}, South Korea"]
    # 상세주소(콤마 뒤)를 떼고 한 번 더 시도한다. 콤마를 공백으로 바꾸기 *전에*
    # 판단해야 하며, 예전 코드는 순서가 뒤바뀌어 이 분기를 타지 못했다.
    if "," in addr:
        first_part = flatten(addr.split(",")[0])
        if first_part and first_part != full:
            variants.append(f"{first_part}, South Korea")
    return variants


def _geocode_address(geocode, raw_addr: str):
    """Geocode one address.

    Returns (coords, had_error) where coords is (lat, lon) or None. `had_error`
    marks a transient failure: the caller must not cache those, otherwise one
    network hiccup blacklists the address forever.
    """
    had_error = False
    for query in _clean_address(raw_addr):
        try:
            location = geocode(query)
        except GeocoderQueryError as exc:
            # 질의 자체가 잘못된 경우 — 재시도해도 의미 없으므로 다음 변형으로.
            print(f"    ! 잘못된 질의 {query!r}: {exc}")
            continue
        except GeocoderServiceError as exc:
            had_error = True
            print(f"    ! 지오코더 오류 {query!r}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - 알 수 없는 실패도 캐싱하지 않는다
            had_error = True
            print(f"    ! 예상치 못한 지오코딩 실패 {query!r}: {type(exc).__name__}: {exc}")
            continue
        if location:
            return (location.latitude, location.longitude), had_error
    return None, had_error


def geocode_missing(df: pd.DataFrame, geocode, cache: dict) -> pd.DataFrame:
    missing = df[df["lat"].isna() | df["lon"].isna()].index
    if missing.empty:
        return df

    total = len(missing)
    print(f"  Geocoding {total} entries ...")
    resolved = failed = skipped = 0
    pending_writes = 0

    for idx in missing:
        raw_addr = _safe_str(df.at[idx, "address"])
        if not raw_addr:
            skipped += 1
            continue

        if raw_addr in cache:
            cached = cache[raw_addr]
            if cached:
                df.at[idx, "lat"] = cached[0]
                df.at[idx, "lon"] = cached[1]
            continue

        coords, had_error = _geocode_address(geocode, raw_addr)
        if coords:
            df.at[idx, "lat"] = coords[0]
            df.at[idx, "lon"] = coords[1]
            cache[raw_addr] = [coords[0], coords[1]]
            resolved += 1
        elif had_error:
            # 일시적 실패 — 캐싱하지 않고 다음 실행에서 다시 시도한다.
            failed += 1
            continue
        else:
            cache[raw_addr] = None
            failed += 1

        pending_writes += 1
        if pending_writes >= CACHE_SAVE_EVERY:
            _save_cache(cache)
            pending_writes = 0

    if pending_writes:
        _save_cache(cache)
    print(f"    resolved={resolved} failed={failed} no-address={skipped}")
    return df


def to_geojson(df: pd.DataFrame) -> dict:
    features = []
    for _, row in df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["lon"]), float(row["lat"])],
                },
                "properties": {
                    "title": _safe_str(row["title"]),
                    "address": _safe_str(row["address"]),
                    "phone": _safe_str(row["phone"]),
                    "category": _safe_str(row["category"]) or DEFAULT_CATEGORY,
                    "link": _safe_str(row["link"]) or "[]",
                    "source": _safe_str(row["source"]),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _parse_links(row) -> list[dict]:
    """Read a row's `link` cell, which is either a raw URL or a JSON array."""
    link_val = _safe_str(row["link"])
    if not link_val:
        return []
    try:
        links = json.loads(link_val)
    except json.JSONDecodeError:
        return [{"link": link_val, "source": _safe_str(row["source"])}]
    if not isinstance(links, list):
        return []
    return [item for item in links if isinstance(item, dict) and item.get("link")]


def consolidate_group(group: pd.DataFrame) -> pd.Series:
    """Collapse rows describing the same store into one feature."""
    # 우선순위: Redtable 주소를 최우선으로 선택, 없으면 가장 긴 주소 선택
    redtable_row = group[group["source"] == "redtable"]
    if not redtable_row.empty:
        address = redtable_row["address"].iloc[0]
    else:
        address = group.loc[group["address"].astype(str).str.len().idxmax(), "address"]

    # lat/lon이 존재하는 행을 우선 선택
    valid_lat = group["lat"].dropna()
    valid_lon = group["lon"].dropna()
    lat = valid_lat.iloc[0] if not valid_lat.empty else float("nan")
    lon = valid_lon.iloc[0] if not valid_lon.empty else float("nan")

    items = []
    extracted_id = None
    for _, row in group.iterrows():
        for item in _parse_links(row):
            items.append(item)
            if not extracted_id:
                match = re.search(r"/(?:food|store)/(\d+)", str(item["link"]))
                if match:
                    extracted_id = match.group(1)

    # 한 소스에서만 잡힌 매장도 나머지 소스 링크를 복원해 준다.
    if extracted_id:
        all_sources = {
            "redtable": f"https://redtable.global/ko/food/{extracted_id}",
            "ydp": f"https://ydp.redtable.global/store/{extracted_id}",
            "benepia": f"https://benepia.redtable.global/store/{extracted_id}",
        }
        known = {item["link"] for item in items}
        for source, url in all_sources.items():
            if url not in known:
                items.append({"link": url, "source": source})

    unique_items = []
    seen = set()
    for item in items:
        key = (item["link"], item.get("source", ""))
        if key not in seen:
            unique_items.append({"link": item["link"], "source": item.get("source", "")})
            seen.add(key)

    # 대표 카테고리: 비어 있지 않은 첫 값
    categories = [c for c in group["category"].map(_safe_str) if c]
    phones = [p for p in group["phone"].map(_safe_str) if p]

    return pd.Series(
        {
            "title": group["title"].iloc[0],
            "address": address,
            "phone": phones[0] if phones else "",
            "category": categories[0] if categories else DEFAULT_CATEGORY,
            "link": json.dumps(unique_items, ensure_ascii=False),
            "lat": lat,
            "lon": lon,
            "source": "combined",
        }
    )


def jitter_overlapping(df: pd.DataFrame) -> pd.DataFrame:
    """Fan out stores sharing an exact coordinate so every marker is clickable."""
    valid = df[df["lat"].notna() & df["lon"].notna()]
    if valid.empty:
        return df
    for (lat, lon), indices in valid.groupby(["lat", "lon"]).groups.items():
        count = len(indices)
        if count < 2:
            continue
        for i, row_idx in enumerate(indices):
            angle = (i / count) * 2 * math.pi
            df.at[row_idx, "lat"] = lat + math.cos(angle) * JITTER_DEG
            df.at[row_idx, "lon"] = lon + math.sin(angle) * JITTER_DEG
    return df


def main() -> int:
    print("=" * 60)
    print("  Redtable Map Data Consolidator")
    print("=" * 60)
    print(f"  source dir: {GOODS_TOOLS_DIR}")

    cache = _load_cache()
    geocode = _init_geocoder()
    source_dfs = []

    for pattern, label, has_coords in CSV_PATTERNS:
        path = find_latest_csv(pattern)
        if not path:
            print(f"  ! {label}: '{pattern}' 에 해당하는 CSV 없음 — 건너뜀")
            continue
        df = load_and_normalize(path, label)
        print(f"  {label}: {os.path.basename(path)} ({len(df)} rows)")
        if not has_coords:
            df = geocode_missing(df, geocode, cache)
        source_dfs.append(df)

    if not source_dfs:
        print(f"\n!! 처리할 CSV를 하나도 찾지 못했습니다. GOODS_TOOLS_DIR={GOODS_TOOLS_DIR}")
        print("!! 수집기가 먼저 실행됐는지, 경로가 맞는지 확인하세요.")
        _save_cache(cache)
        return 1

    combined = pd.concat(source_dfs, ignore_index=True)
    raw_count = len(combined)

    combined["clean_title"] = combined["title"].apply(normalize_text)
    combined["base_address"] = combined["address"].apply(get_base_address)

    combined = (
        combined.groupby(["clean_title", "base_address"], group_keys=False)
        .apply(consolidate_group, include_groups=False)
        .reset_index(drop=True)
    )
    combined = jitter_overlapping(combined)

    geojson = to_geojson(combined)
    _write_json_atomic(OUTPUT_FILE, geojson)
    _save_cache(cache)

    dropped = len(combined) - len(geojson["features"])
    print(f"\n  {raw_count} rows -> {len(combined)} stores -> {len(geojson['features'])} features")
    if dropped:
        print(f"  ! 좌표가 없어 제외된 매장 {dropped}건")
    print(f"  wrote {OUTPUT_FILE}")
    print("✨ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
