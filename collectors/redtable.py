"""RedTable 맛집(must-eat) 목록 + 매장 상세 수집기.

목록 페이지에서 매장 링크를 모으고, 매장별 상세 페이지에서 주소·전화번호·
카테고리·좌표를 읽는다. 항목 1건이 깨져도 전체 수집이 멈추지 않는다.
"""

import os
import re
import time

try:  # `python collectors/redtable.py` 와 `python -m collectors.redtable` 를 모두 지원
    from common import fetch_soup, make_session, run, save_csv, text_of
except ImportError:  # pragma: no cover
    from collectors.common import fetch_soup, make_session, run, save_csv, text_of

LIST_URL = "https://redtable.global/ko/must-eat/load-more"
OUTPUT_PREFIX = "must_eat_data"

LIST_PARAMS = {
    "s_commercial_area_id": 234,
    "s_must_eat_id": 8849,
    "s_channel": "redtable",
    "tit_flag": 2,
}

CSV_COLUMNS = ["Title", "Link", "Address", "Phone", "Category", "Latitude", "Longitude"]

# 예전에는 5페이지로 하드코딩되어 그 뒤 데이터가 조용히 누락됐다. 이제 카드가
# 없을 때까지 진행하고, 상한은 폭주 방지용이며 도달하면 경고를 남긴다.
MAX_OFFSET = int(os.environ.get("REDTABLE_MAX_OFFSET", "30"))
# 상세 페이지는 매장당 1회씩 요청하므로 간격을 둔다.
DETAIL_DELAY_S = float(os.environ.get("REDTABLE_DETAIL_DELAY_S", "1.0"))

# 구버전 마크업: <a href="...query=37.5,126.9">
LEGACY_QUERY_RE = re.compile(r"query=(-?[\d.]+),\s*(-?[\d.]+)")
# 현재 마크업: div.find-route 의 onclick 안 destination=${encodeURI('37.5,126.9')}
COORD_PAIR_RE = re.compile(r"(-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
# 한반도 대략 범위 — 엉뚱한 숫자쌍을 좌표로 오인하지 않기 위한 검증
LAT_RANGE = (33.0, 39.5)
LON_RANGE = (124.0, 132.0)


def _extract_link(card) -> str:
    """Pull the store URL out of the card's onclick handler."""
    onclick = card.get("onclick") or ""
    match = re.search(r"'(https?://[^']+)'", onclick)
    if not match:
        return ""
    return match.group(1).replace("/food/", "/ko/food/", 1)


def _valid_coords(lat: str, lon: str) -> bool:
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return LAT_RANGE[0] <= lat_f <= LAT_RANGE[1] and LON_RANGE[0] <= lon_f <= LON_RANGE[1]


def _parse_coords(store_soup) -> tuple[str, str]:
    """Pull the store coordinates out of whichever map markup the page uses.

    사이트가 지도 링크 구조를 바꾼 적이 있어(<a href=...query=> -> div.find-route
    의 onclick) 두 형태를 모두 시도하고, 마지막에 페이지 전체를 훑는다. 좌표를
    놓치면 redtable 행은 지오코딩 대상도 아니어서 지도에서 그대로 사라진다.
    """
    store_map = store_soup.find("div", class_="store-map")
    scopes = [scope for scope in (store_map, store_soup) if scope is not None]

    for scope in scopes:
        for anchor in scope.find_all("a", href=True):
            match = LEGACY_QUERY_RE.search(anchor["href"])
            if match and _valid_coords(*match.groups()):
                return match.group(1), match.group(2)
        for match in COORD_PAIR_RE.finditer(str(scope)):
            if _valid_coords(*match.groups()):
                return match.group(1), match.group(2)
    return "", ""


def _parse_store_detail(store_soup) -> dict:
    business_time = store_soup.find("div", class_="business-time")
    phone = text_of(business_time.find("p")) if business_time else ""

    category = text_of(store_soup.find("h4", class_="store-label"))
    category = category.split("|")[0].strip() if category else ""

    latitude, longitude = _parse_coords(store_soup)
    return {
        "Address": text_of(store_soup.find("h5", id="address")),
        "Phone": phone,
        "Category": category,
        "Latitude": latitude,
        "Longitude": longitude,
    }


def _collect_cards(session) -> list[dict]:
    """Walk the offset-paged must-eat list, returning {Title, Link} entries."""
    cards: list[dict] = []
    seen_links: set[str] = set()

    for offset in range(1, MAX_OFFSET + 1):
        params = dict(LIST_PARAMS, offset=offset)
        soup = fetch_soup(session, LIST_URL, params=params)
        if soup is None:
            print(f"[오프셋 {offset}] 목록을 가져오지 못해 중단합니다.")
            break

        found = soup.find_all("div", class_="card-musteat")
        if not found:
            print(f"[오프셋 {offset}] 카드가 없어 종료합니다.")
            break

        added = 0
        for card in found:
            title = text_of(card.find("h3", class_="musteat-title"))
            link = _extract_link(card)
            if not title or not link or link in seen_links:
                continue
            seen_links.add(link)
            cards.append({"Title": title, "Link": link})
            added += 1

        print(f"[오프셋 {offset}] 카드 {len(found)}개 / 신규 {added}개")
    else:
        print(f"  ! 오프셋 상한({MAX_OFFSET})에 도달했습니다. REDTABLE_MAX_OFFSET 을 늘려보세요.")

    return cards


def main() -> int:
    session = make_session()
    cards = _collect_cards(session)
    print(f"목록에서 찾은 매장: {len(cards)}개")
    if not cards:
        print("!! 목록이 비어 있어 CSV 를 쓰지 않습니다.")
        return 1

    rows = []
    detail_failures = 0
    for i, card in enumerate(cards, 1):
        store_soup = fetch_soup(session, card["Link"])
        if store_soup is None:
            detail_failures += 1
        else:
            try:
                rows.append({**card, **_parse_store_detail(store_soup)})
            except Exception as exc:  # noqa: BLE001 - 1건 실패로 전체를 죽이지 않는다
                print(f"  ! 상세 파싱 실패 {card['Link']}: {type(exc).__name__}: {exc}")
                detail_failures += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(cards)} 처리")
        if i < len(cards):
            time.sleep(DETAIL_DELAY_S)

    print(f"상세 수집 완료: {len(rows)}건 (실패 {detail_failures}건)")
    if not rows:
        print("!! 상세 정보를 한 건도 못 가져와 CSV 를 쓰지 않습니다.")
        return 1

    save_csv(rows, OUTPUT_PREFIX, columns=CSV_COLUMNS)
    return 0


if __name__ == "__main__":
    run(main)
