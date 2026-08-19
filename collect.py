# -*- coding: utf-8 -*-
"""울산 아파트 법원경매 공개 목록 수집기.

공개 검색목록에서 읽을 수 있는 범위만 수집한다. 공개 목록의 건물면적은
전용면적과 다를 수 있으므로, 사이트에서도 '건물면적(공개목록)'이라고
표시하고 상세 확인이 필요한 항목으로 안내한다.

사용법:
    python collect.py
    python collect.py --history-days 120 --delay 0.08
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / "data" / "auctions.json"
SEARCH_URL = "https://www.winnerauction.co.kr/search/search_list.php"
CALENDAR_URL = "https://www.winnerauction.co.kr/search/calendar_list.php"
OFFICIAL_URL = "https://www.courtauction.go.kr/"
MARKET_URL = "https://rt.molit.go.kr/pt/gis/gis.do?mobileAt=&srhThingSecd=C"
SOURCE_NAME = "위너옥션 공개 검색목록"
SOURCE_KIND = "보조 공개목록"

APT = "아파트"
COURT = "411"  # 울산지방법원
ALLOWED_DISTRICTS = ("중구", "남구", "북구")
EXCLUDED_DISTRICTS = ("동구", "울주군")
STATUS_WORDS = ("매각", "유찰", "변경", "취하", "진행", "신건")
MONEY_RE = re.compile(r"\d[\d,]*")
DATE_RE = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")


def clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def first_text(node: Any, selector: str) -> str:
    found = node.select_one(selector)
    return clean(found.get_text(" ", strip=True)) if found else ""


def parse_date(value: str) -> str:
    match = DATE_RE.search(value or "")
    if not match:
        return ""
    year, month, day = (int(x) for x in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def parse_money(value: str) -> int | None:
    value = clean(value)
    match = MONEY_RE.search(value)
    return int(match.group(0).replace(",", "")) if match else None


def parse_pyeong(value: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}\s*([\d.]+)\s*평", value or "")
    return float(match.group(1)) if match else None


def format_source_url(base: str, params: dict[str, str]) -> str:
    return f"{base}?{urlencode(params)}"


def page_parts(tr: Any) -> list[str]:
    return [clean(x) for x in tr.stripped_strings if clean(x)]


def extract_complex(address: str) -> str:
    """주소에서 화면에 보여줄 단지명을 보수적으로 추출한다."""
    # '... 에일린의뜰1차아파트 102동 ...' 같은 표기를 우선 사용한다.
    match = re.search(
        r"([가-힣A-Za-z0-9·&.\-]+(?:아파트|자이|푸르지오|힐스테이트|캐슬|위브|더샵|하늘채|센트럴|타운|뜰|마을))",
        address,
    )
    if match:
        return match.group(1).strip()

    # 괄호 안 단지명이 있는 경우 마지막 토큰을 사용한다.
    groups = re.findall(r"\(([^)]+)\)", address)
    if groups:
        candidate = groups[-1].split(",")[-1].strip()
        if candidate:
            return candidate

    # 최후의 fallback은 주소 앞부분이다.
    return address.split(",")[-1].strip()[:40] or "단지명 확인 필요"


def extract_district(address: str) -> str:
    match = re.search(r"울산광역시\s+(중구|남구|북구|동구|울주군)", address or "")
    return match.group(1) if match else ""


def is_in_scope(address: str) -> bool:
    if "울산광역시" not in address:
        return False
    district = extract_district(address)
    return district in ALLOWED_DISTRICTS and district not in EXCLUDED_DISTRICTS


def extract_risk_tags(tr: Any, area_text: str) -> list[str]:
    detail = " ".join(clean(x.get_text(" ", strip=True)) for x in tr.select("ul.list_sell02 li"))
    tags: list[str] = []
    for raw in re.findall(r"\[([^\]]+)\]", detail):
        tag = clean(raw).strip(" ,")
        if not tag or "토지" in tag or "건물" in tag or "평" in tag:
            continue
        if tag not in tags:
            tags.append(tag)
    return tags


def row_to_auction(tr: Any, source_url: str, today: date) -> dict[str, Any] | None:
    parts = page_parts(tr)
    list_one = tr.select_one("ul.list_sell01")
    status_lists = [
        node for node in tr.select("ul.list_sell01")
        if any(word in clean(node.get_text(" ", strip=True)) for word in STATUS_WORDS)
    ]
    status_list = status_lists[-1] if status_lists else list_one
    list_one_text = clean(status_list.get_text(" ", strip=True)) if status_list else ""

    category = first_text(tr, "ul.list_sell01 li.lest_test02")
    if category != APT:
        return None

    address = first_text(tr, "ul.list_sell02 li.lest_test05")
    if not address or not is_in_scope(address):
        return None

    bid_date = parse_date(" ".join(parts))
    case_no = first_text(tr, "ul.list_sell02 li.lest_test06")
    if not case_no:
        # 검색 목록의 페이지 구조가 바뀌었을 때를 위한 fallback.
        for value in parts:
            if re.fullmatch(r"20\d{2}-\d+\s*(?:\[\d+\])?", value):
                case_no = value
                break
    if not case_no:
        return None

    area_text = first_text(tr, "ul.list_sell02 li.lest_test02")
    land_pyeong = parse_pyeong(area_text, "토지")
    building_pyeong = parse_pyeong(area_text, "건물")
    building_m2 = round(building_pyeong * 3.305785, 2) if building_pyeong is not None else None

    appraisal = parse_money(first_text(tr, "ul.list_sell03 li.lest_test03"))
    minimum = parse_money(first_text(tr, "ul.list_sell03 li.lest_test04"))
    final_price = parse_money(first_text(tr, "ul.list_sell03 li.lest_test07"))

    status = next((word for word in STATUS_WORDS if word in list_one_text), "확인 필요")
    round_match = re.search(r"\((\d+)회\)", list_one_text)
    auction_round = int(round_match.group(1)) if round_match else None
    percentages = [int(x) for x in re.findall(r"\((\d+)%\)", list_one_text)]
    minimum_ratio = percentages[0] if percentages else None
    final_ratio = percentages[1] if len(percentages) > 1 else None
    if minimum_ratio is None and appraisal and minimum:
        minimum_ratio = round(minimum / appraisal * 100)

    district = extract_district(address)
    risk_tags = extract_risk_tags(tr, area_text)
    is_interest = building_pyeong is not None and 24 <= building_pyeong <= 40
    upcoming = bool(bid_date and date.fromisoformat(bid_date) >= today and status not in ("매각", "취하"))
    discount = round((1 - minimum / appraisal) * 100, 1) if appraisal and minimum else None

    return {
        "id": f"winner:{case_no}:{bid_date}:{address}",
        "case_no": case_no,
        "case_display": case_no.replace("-", "타경", 1),
        "court": first_text(tr, "ul.list_sell01 li:nth-of-type(3)") or "울산지방법원",
        "category": category,
        "district": district,
        "complex": extract_complex(address),
        "address": address,
        "bid_date": bid_date,
        "status": status,
        "auction_round": auction_round,
        "appraisal": appraisal,
        "minimum_price": minimum,
        "final_price": final_price if status == "매각" else None,
        "minimum_ratio": minimum_ratio,
        "final_ratio": final_ratio,
        "discount_vs_appraisal": discount,
        "market_price": None,
        "market_discount": None,
        "market_note": "국토교통부 실거래가 자동 매칭 전 — 단지명·면적 확인 후 별도 연동",
        "land_pyeong": land_pyeong,
        "building_pyeong": building_pyeong,
        "building_m2": building_m2,
        "supply_pyeong": None,
        "is_interest": is_interest,
        "is_upcoming": upcoming,
        "risk_tags": risk_tags,
        "school_access": "미확인 — 현장·지도 확인 필요",
        "rights_note": (
            f"공개목록 특이사항: {', '.join(risk_tags)}. 상세 권리·임차인 분석이 필요합니다."
            if risk_tags
            else "공개목록만으로 권리·임차인 현황을 확정할 수 없습니다. 원문과 등기·현황조사서를 확인하세요."
        ),
        "area_note": "건물면적(공개목록) 기준 — 전용면적·공급면적은 원문에서 최종 확인",
        "source_name": SOURCE_NAME,
        "source_kind": SOURCE_KIND,
        "source_url": source_url,
        "official_url": OFFICIAL_URL,
    }


def parse_page(html: bytes, source_url: str, today: date) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for tr in soup.select("table.tbl_list tr"):
        item = row_to_auction(tr, source_url, today)
        if item:
            out.append(item)
    return out


def fetch(session: requests.Session, url: str, params: dict[str, str]) -> tuple[bytes, str]:
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content, response.url


def collect_search(session: requests.Session, today: date) -> tuple[list[dict[str, Any]], list[str]]:
    params = {
        "acourt": COURT,
        "acharge": "10",
        "usage_codes": "101",
        "rows": "20",
    }
    html, source_url = fetch(session, SEARCH_URL, params)
    return parse_page(html, source_url, today), [source_url]


def collect_history(
    session: requests.Session,
    today: date,
    history_days: int,
    delay: float,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    records: list[dict[str, Any]] = []
    source_urls: list[str] = []
    errors: list[str] = []
    for offset in range(history_days + 1):
        target = today - timedelta(days=offset)
        params = {
            "acharge": "10",
            "acourt": COURT,
            "aorder": "b.event_year,b.event_no,a.no",
            "ipdate1": target.isoformat(),
        }
        try:
            html, source_url = fetch(session, CALENDAR_URL, params)
            records.extend(parse_page(html, source_url, today))
            source_urls.append(source_url)
        except Exception as exc:  # 한 날짜의 실패가 전체 수집을 막지 않도록 한다.
            errors.append(f"{target.isoformat()}: {exc}")
        if delay:
            time.sleep(delay)
    return records, source_urls, errors


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["id"]
        # 동일 사건이 검색목록과 일정목록에 함께 있으면 일정목록의 주소/상태가 더 자세하다.
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        for field, value in item.items():
            if value not in (None, "", []):
                current[field] = value
    return sorted(
        merged.values(),
        key=lambda x: (x.get("is_upcoming", False), x.get("bid_date", ""), x.get("case_no", "")),
        reverse=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="울산 아파트 경매 공개목록 수집")
    parser.add_argument("--history-days", type=int, default=90, help="최근 일정목록을 훑을 날짜 수")
    parser.add_argument("--delay", type=float, default=0.08, help="일정목록 요청 사이 대기 초")
    args = parser.parse_args()

    today = date.today()
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; UlsanApartmentAuction/1.0; +https://www.courtauction.go.kr/)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
    )

    print(f"울산 아파트 경매 수집 시작  (기준일 {today.isoformat()})")
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    search_urls: list[str] = []
    try:
        current, search_urls = collect_search(session, today)
        items.extend(current)
        print(f"  예정 검색목록: {len(current)}건")
    except Exception as exc:
        errors.append(f"예정 검색목록: {exc}")
        print(f"  예정 검색목록 실패: {exc}")

    history, history_urls, history_errors = collect_history(session, today, max(0, args.history_days), args.delay)
    items.extend(history)
    errors.extend(history_errors)
    print(f"  최근 일정목록: {len(history)}건 ({args.history_days}일 확인)")

    auctions = deduplicate(items)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of": today.isoformat(),
        "history_days": args.history_days,
        "count": len(auctions),
        "filters": {
            "included_districts": list(ALLOWED_DISTRICTS),
            "excluded_districts": list(EXCLUDED_DISTRICTS),
            "building_pyeong_focus": [24, 40],
            "supply_pyeong_focus": 32,
            "school_walk_minutes": 10,
            "large_complex_units": 500,
        },
        "sources": {
            "official": {"name": "대한민국 법원경매정보", "url": OFFICIAL_URL},
            "public_list": {"name": SOURCE_NAME, "kind": SOURCE_KIND, "url": SEARCH_URL},
            "market": {"name": "국토교통부 실거래가 공개시스템", "url": MARKET_URL},
        },
        "source_urls": list(dict.fromkeys(search_urls + history_urls))[:200],
        "errors": errors[:30],
        "auctions": auctions,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    upcoming = sum(1 for item in auctions if item.get("is_upcoming"))
    interests = sum(1 for item in auctions if item.get("is_interest"))
    print(f"완료: {len(auctions)}건 저장  (관심 면적 {interests}건, 입찰 예정 {upcoming}건)")
    print(f"저장 위치: {DATA_PATH}")
    if errors:
        print(f"주의: {len(errors)}개 요청에서 오류가 있었음. 다음 실행에서 재확인하세요.")


if __name__ == "__main__":
    main()
