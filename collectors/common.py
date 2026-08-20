"""collectors/common.py — 수집기 공용 유틸.

HTTP 요청(타임아웃·재시도), 목록 페이지 파싱, CSV 저장을 한곳에 모았다.
ydp / benepia 는 목록 페이지 구조가 완전히 동일하므로 `scrape_store_list`
하나를 URL 만 바꿔 재사용한다.
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 모든 값은 환경변수로 덮어쓸 수 있다.
REQUEST_TIMEOUT_S = float(os.environ.get("COLLECTOR_TIMEOUT_S", "15"))
REQUEST_RETRIES = int(os.environ.get("COLLECTOR_RETRIES", "3"))
MAX_OFFSET = int(os.environ.get("COLLECTOR_MAX_OFFSET", "200"))
# 목록 요청이 이 횟수만큼 연속 실패하면 중단한다(끝없이 도는 것을 막는다).
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("COLLECTOR_MAX_FAILURES", "5"))
OUTPUT_DIR = os.environ.get("COLLECTOR_OUTPUT_DIR", os.getcwd())

CSV_COLUMNS = ["Title", "Address", "Phone", "Category", "Link"]

# 마지막 토큰이 전화번호인지 판별한다. 전화번호가 없는 주소를 통째로 쪼개다
# ValueError 로 전체 수집이 죽는 것을 막기 위한 것.
PHONE_RE = re.compile(r"^\+?\d[\d\-().]{6,}$")


def make_session() -> requests.Session:
    """Session with a shared UA and transient-error retries."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=REQUEST_RETRIES,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_soup(session: requests.Session, url: str, params: dict | None = None):
    """GET a page and parse it. Returns None on any failure (never raises).

    timeout 이 없으면 CI 잡이 무한 대기할 수 있으므로 반드시 지정한다.
    """
    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
    except requests.RequestException as exc:
        print(f"  ! 요청 실패 {url}: {type(exc).__name__}: {exc}")
        return None
    if response.status_code != 200:
        print(f"  ! 상태 코드 {response.status_code}: {response.url}")
        return None
    return BeautifulSoup(response.content, "html.parser")


def text_of(node, default: str = "") -> str:
    """Safe `get_text` for a node that may be None.

    구분자 " " 는 필수다. 자식 태그로 감싼 값(예: 주소 뒤 <span>전화번호</span>)이
    구분자 없이 이어 붙으면 "…로 5002-789-5751" 처럼 뭉개진다.
    """
    if node is None:
        return default
    return " ".join(node.get_text(" ", strip=True).split())


def split_address_phone(text: str) -> tuple[str, str]:
    """Split '주소 전화번호' — only when the tail really looks like a number."""
    text = " ".join((text or "").split())
    if not text:
        return "", ""
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and PHONE_RE.match(parts[1]):
        return parts[0].strip(), parts[1].strip()
    return text, ""


def _parse_place(place) -> dict | None:
    """Parse one store card from a ydp/benepia list page."""
    store_name = text_of(place.find("h3", id="store_name"))
    if not store_name:
        return None

    # 주소/전화번호는 <p id="store_name2">주소 <span>전화</span></p> 구조다.
    # span 이 있으면 구조로 나누고, 없으면 문자열 휴리스틱으로 되돌린다.
    detail = place.find("p", id="store_name2")
    phone_span = detail.find("span") if detail else None
    if phone_span is not None:
        phone = text_of(phone_span)
        phone_span.extract()
        address = text_of(detail)
    else:
        address, phone = split_address_phone(text_of(detail))
    address = address.rstrip(",").strip()
    # 전화번호가 여러 개면 ", " 로 정돈한다.
    phone = re.sub(r"\s*,\s*", ", ", phone).strip(" ,")

    category_span = place.find("span", class_="cate-nm")
    category = text_of(category_span).split(",")[0].strip() if category_span else ""

    anchor = place.find("a", href=True)
    link = anchor["href"].strip() if anchor else ""

    return {
        "Title": store_name,
        "Address": address,
        "Phone": phone,
        "Category": category,
        "Link": link,
    }


def scrape_store_list(label: str, url_template: str, output_prefix: str) -> int:
    """Walk the offset-paged store list until it runs dry, then write a CSV."""
    session = make_session()
    rows: list[dict] = []
    seen_links: set[str] = set()
    parse_failures = 0
    consecutive_failures = 0
    last_offset = 0

    for offset in range(1, MAX_OFFSET + 1):
        last_offset = offset
        soup = fetch_soup(session, url_template.format(offset))
        if soup is None:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"  ! 연속 {consecutive_failures}회 실패 — 중단합니다.")
                break
            continue
        consecutive_failures = 0

        places = soup.find_all("div", class_="col-lg-4 col-md-4")
        if not places:
            print(f"[오프셋 {offset}] 카드가 없어 종료합니다.")
            break

        added = 0
        for place in places:
            try:
                row = _parse_place(place)
            except Exception as exc:  # noqa: BLE001 - 항목 1건 실패로 전체를 죽이지 않는다
                print(f"  ! 카드 파싱 실패: {type(exc).__name__}: {exc}")
                parse_failures += 1
                continue
            if row is None:
                parse_failures += 1
                continue
            if row["Link"] and row["Link"] in seen_links:
                continue
            if row["Link"]:
                seen_links.add(row["Link"])
            rows.append(row)
            added += 1

        print(f"[오프셋 {offset}] 카드 {len(places)}개 / 수집 {added}개")
    else:
        print(f"  ! 오프셋 상한({MAX_OFFSET})에 도달했습니다. 남은 데이터가 있을 수 있습니다.")

    print(f"총 수집된 가게 수: {len(rows)} (오프셋 {last_offset}까지, 파싱 실패 {parse_failures}건)")
    if not rows:
        print(f"!! {label}: 수집 결과가 비어 있어 CSV 를 쓰지 않습니다.")
        return 1

    save_csv(rows, output_prefix)
    return 0


def save_csv(rows: list[dict], output_prefix: str, columns: list[str] | None = None) -> str:
    """Write rows to `<OUTPUT_DIR>/<prefix>_YYYYMMDD.csv`, sorted by title."""
    columns = columns or CSV_COLUMNS
    df = pd.DataFrame(rows, columns=columns).sort_values(by="Title", kind="stable")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{output_prefix}_{datetime.now().strftime('%Y%m%d')}.csv"
    path = os.path.join(OUTPUT_DIR, filename)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Data saved to {path}")
    return path


def run(main_func) -> None:
    """Entry-point wrapper: turn the return value into a process exit code."""
    sys.exit(main_func() or 0)
