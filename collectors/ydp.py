"""영등포구청 채널 매장 목록 수집기."""

try:  # `python collectors/ydp.py` 와 `python -m collectors.ydp` 를 모두 지원
    from common import run, scrape_store_list
except ImportError:  # pragma: no cover
    from collectors.common import run, scrape_store_list

BASE_URL = "https://ydp.redtable.global/ko/storeLoad?s_loc1=Korea&offset={}"
OUTPUT_PREFIX = "ydp_store_data"


def main() -> int:
    return scrape_store_list("ydp", BASE_URL, OUTPUT_PREFIX)


if __name__ == "__main__":
    run(main)
