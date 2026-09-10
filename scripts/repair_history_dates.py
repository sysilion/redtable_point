#!/usr/bin/env python3
"""repair_history_dates.py — 롤백 커밋이 오염시킨 관측일을 되돌린다. (1회성)

2026-09-10 에 두 개의 로컬 커밋(648d437, ce06f76)이 6월 CSV 로 만든
map_data.json 을 커밋했다. 그 상태에서 store_history.json 을 부트스트랩했기
때문에, 7~8월에 이미 목록에서 빠진 매장들까지 "2026-09-10 에 관측됨" 으로
기록됐다. 그 결과 다음 CI 실행에서 25곳이 한꺼번에, 그것도 틀린 날짜로
'사라짐' 묘비가 됐다.

이 스크립트는 매장 목록을 건드리지 않는다. store_history.json 의 날짜만
git 이력에서 다시 계산하고, 그 결과로 map_data.json 의 묘비 집합을 다시 만든다.

증거 규칙:
  - 정상 스냅샷(롤백 커밋 제외)에 있으면 그 커밋 날짜에 실재했다.
    first_seen / last_seen 양쪽 근거가 된다.
  - 롤백 커밋에 있으면 그 CSV 가 찍힌 2026-06-22 에 실재했다는 뜻일 뿐,
    9월에도 있었다는 근거는 아니다. first_seen 에만 반영한다.
  - status 가 'gone' 인 Feature 는 관측이 아니라 묘비다. 근거에서 뺀다.

Usage:
    python3 scripts/repair_history_dates.py [--dry-run]
"""

import json
import subprocess
import sys
from datetime import date

from consolidate import (
    HISTORY_VERSION,
    HISTORY_FILE,
    OUTPUT_FILE,
    _load_history,
    _save_history,
    _write_json_atomic,
    apply_history,
    store_key,
)

TRACKED_PATH = "data/map_data.json"

# 6월 CSV 로 만들어진 커밋들. 관측 근거로 쓰면 안 된다.
ROLLBACK_COMMITS = {"648d437": "2026-06-22", "ce06f76": "2026-06-22"}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def _commits() -> list[tuple[str, str]]:
    out = _git(
        "log", "--follow", "--date=short", "--format=%H\t%ad", "--", TRACKED_PATH
    )
    rows = []
    for line in out.splitlines():
        sha, _, day = line.partition("\t")
        if sha and day:
            rows.append((sha, day))
    rows.reverse()
    return rows


def _live_keys_at(sha: str) -> set[str]:
    """그 커밋 시점에 '살아 있던' 매장 키. 묘비는 뺀다."""
    try:
        blob = _git("show", f"{sha}:{TRACKED_PATH}")
        features = (json.loads(blob) or {}).get("features") or []
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return set()
    keys = set()
    for feature in features:
        props = (feature or {}).get("properties")
        if isinstance(props, dict) and props.get("status") != "gone":
            keys.add(store_key(props))
    return keys


def _rollback_date(sha: str) -> str | None:
    for prefix, csv_date in ROLLBACK_COMMITS.items():
        if sha.startswith(prefix):
            return csv_date
    return None


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    first_evidence: dict[str, str] = {}
    last_evidence: dict[str, str] = {}
    skipped = []

    for sha, day in _commits():
        keys = _live_keys_at(sha)
        if not keys:
            continue
        rollback = _rollback_date(sha)
        if rollback is not None:
            skipped.append(f"{sha[:7]}({day})")
            for key in keys:
                # 존재했다는 사실만 인정하고, 날짜는 CSV 가 찍힌 날로 본다.
                if key not in first_evidence or rollback < first_evidence[key]:
                    first_evidence[key] = rollback
            continue
        for key in keys:
            first_evidence.setdefault(key, day)
            last_evidence[key] = day

    print(f"  근거로 쓴 정상 스냅샷 밖의 롤백 커밋: {', '.join(skipped) or '없음'}")

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    active = [f for f in geojson["features"] if f["properties"].get("status") != "gone"]
    active_keys = {store_key(f["properties"]) for f in active}
    print(f"  현재 활성 매장 {len(active_keys)}곳 · 기존 묘비 {len(geojson['features']) - len(active)}곳")

    history = _load_history()
    stores = history["stores"]
    fixed_first = fixed_last = dropped = 0

    for key in list(stores.keys()):
        record = stores[key]
        true_first = first_evidence.get(key)
        current_first = str(record.get("first_seen") or "")
        if true_first and (not current_first or true_first < current_first):
            record["first_seen"] = true_first
            fixed_first += 1

        if key in active_keys:
            continue  # 오늘 CI 가 실제로 봤다. last_seen 은 그대로 둔다.

        true_last = last_evidence.get(key)
        if not true_last:
            # 정상 스냅샷에 한 번도 없었다. 묘비를 세울 근거가 없다.
            del stores[key]
            dropped += 1
            continue
        if str(record.get("last_seen") or "") != true_last:
            record["last_seen"] = true_last
            fixed_last += 1

    print(f"  first_seen 보정 {fixed_first}건 · last_seen 보정 {fixed_last}건 · 근거 없어 삭제 {dropped}건")

    geojson["features"] = active
    counts = apply_history(geojson, history, {}, date.today())
    print(f"  결과: 신규 {counts['new']}곳 · 사라짐 {counts['gone']}곳 (총 {counts['total']}개 마커)")

    if dry_run:
        print("  (--dry-run) 파일을 쓰지 않았습니다.")
        return 0

    _write_json_atomic(OUTPUT_FILE, geojson)
    _save_history(history, date.today())
    print(f"  wrote {OUTPUT_FILE}")
    print(f"  wrote {HISTORY_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
