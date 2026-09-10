#!/usr/bin/env python3
"""bootstrap_history.py — data/map_data.json 의 git 이력에서 매장 이력을 복원한다.

consolidate.py 는 store_history.json 이 없으면 이번 주를 기준점으로만 잡고
아무것도 '신규'로 표시하지 않는다. 이 저장소에는 이미 수개월치 주간 갱신
커밋이 쌓여 있으므로, 그 커밋들을 되짚어 매장별 최초/최종 관측일을 만들면
첫 주부터 진짜 신규·사라짐을 보여줄 수 있다.

한 번만 실행하면 된다. 그 뒤로는 consolidate.py 가 이력을 이어서 갱신한다.

Usage:
    python3 scripts/bootstrap_history.py [--dry-run]
"""

import json
import subprocess
import sys
from datetime import date

from consolidate import (
    GONE_RETENTION_DAYS,
    HISTORY_FILE,
    HISTORY_VERSION,
    OUTPUT_FILE,
    _days_since,
    _save_history,
    _write_json_atomic,
    apply_history,
    store_key,
)

TRACKED_PATH = "data/map_data.json"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def _commits() -> list[tuple[str, str]]:
    """(sha, YYYY-MM-DD) 목록을 오래된 순으로.

    `--reverse` 를 `--follow` 와 같이 주면 git 이 첫 커밋 하나만 뱉는다.
    (--follow 는 경로 추적을 위해 커밋을 하나씩 흘려보내는데 --reverse 가 그
    스트림을 잘라먹는다.) 최신순으로 받아 파이썬에서 뒤집는다.
    """
    out = _git(
        "log", "--follow", "--date=short",
        "--format=%H\t%ad", "--", TRACKED_PATH,
    )
    rows = []
    for line in out.splitlines():
        sha, _, day = line.partition("\t")
        if sha and day:
            rows.append((sha, day))
    rows.reverse()
    return rows


def _features_at(sha: str) -> list[dict]:
    try:
        blob = _git("show", f"{sha}:{TRACKED_PATH}")
    except subprocess.CalledProcessError:
        return []
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return []
    features = (payload or {}).get("features")
    return features if isinstance(features, list) else []


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    commits = _commits()
    if not commits:
        print(f"!! {TRACKED_PATH} 의 커밋 이력을 찾지 못했습니다.")
        return 1

    print(f"  커밋 {len(commits)}개를 되짚습니다 ({commits[0][1]} → {commits[-1][1]})")

    stores: dict[str, dict] = {}

    for sha, day in commits:
        features = _features_at(sha)
        if not features:
            continue
        for feature in features:
            props = (feature or {}).get("properties")
            if not isinstance(props, dict):
                continue
            # 예전 결과에도 status 가 섞여 들어갈 수 있다. 날짜 계산은 커밋
            # 날짜만 믿는다.
            key = store_key(props)
            record = stores.setdefault(key, {"first_seen": day})
            record["last_seen"] = day

    today = date.today()
    current = {store_key(f["properties"]) for f in _features_at("HEAD")}

    # 지금 목록에 없는 매장은 기록만 남기고 '사라짐' 으로 세우지 않는다.
    # git 이력은 "그날 커밋된 지도에 있었는가" 만 알려줄 뿐, 빠진 이유가
    # 제휴 종료인지 지오코딩 실패인지 구분해 주지 못한다. 잘못된 묘비를
    # 세우느니 다음 주간 실행이 진짜 diff 를 잡게 둔다. 기록을 남겨 두는
    # 이유는, 그 매장이 돌아왔을 때 first_seen 을 이어 붙여 '신규' 오탐을
    # 막기 위해서다.
    kept = {}
    dormant = 0
    for key, record in stores.items():
        if key in current:
            kept[key] = record
            continue
        gone_days = _days_since(record.get("last_seen"), today)
        if gone_days is None or gone_days > GONE_RETENTION_DAYS:
            continue
        kept[key] = record
        dormant += 1

    history = {"version": HISTORY_VERSION, "stores": kept}
    active = len(kept) - dormant
    print(f"  현재 매장 {active}곳 · 최근 목록에서 빠진 매장 {dormant}곳(표시 안 함)")

    horizon = min(len(commits), 6)
    recent = sorted({day for _, day in commits[-horizon:]})
    print(f"  최근 관측일: {', '.join(recent)}")

    # 이력만 만들어 두면 다음 주 실행까지 지도에는 아무 표시도 뜨지 않는다.
    # 지금 배포된 map_data.json 에도 곧바로 status 를 입혀 준다. 수집기를 다시
    # 돌리지 않으므로 좌표·목록은 그대로다.
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    counts = apply_history(geojson, history, {}, today)
    print(
        f"  map_data.json: 신규 {counts['new']}곳 · 사라짐 {counts['gone']}곳 "
        f"(총 {counts['total']}개 마커)"
    )

    if dry_run:
        print("  (--dry-run) 파일을 쓰지 않았습니다.")
        return 0

    _write_json_atomic(OUTPUT_FILE, geojson)
    _save_history(history, today)
    print(f"  wrote {OUTPUT_FILE}")
    print(f"  wrote {HISTORY_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
