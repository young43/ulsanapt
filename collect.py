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
ONBID_SEARCH_URL = "https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do"
ONBID_LIST_URL = "https://www.onbid.co.kr/op/cltrpbancinf/clbtcltrclg/cltrclbtcltrclg/CltrClbtCltrClgController/inqCltrClbtRlstClg.do"
ONBID_DETAIL_URL = "https://www.onbid.co.kr/op/cltrpbancinf/cltrdtl/CltrDtlController/mvmnCltrDtl.do"
ONBID_SOURCE_NAME = "\uc628\ube44\ub4dc \uacf5\uc2dd \uac80\uc0c9\ubaa9\ub85d"
ONBID_SOURCE_KIND = "\uc628\ube44\ub4dc \uacf5\ub9e4 \uacf5\uac1c\ubaa9\ub85d"
ONBID_CATEGORY_ID = "10200"  # \uc628\ube44\ub4dc \ubd80\ub3d9\uc0b0 > \uc8fc\uac70\uc6a9\uac74\ubb3c
ONBID_DISTRICT_PREFIX = "\uc6b8\uc0b0\uad11\uc5ed\uc2dc"
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


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_onbid_complex(address: str, category: str) -> str:
    """온비드 물건명에서 단지명 또는 화면용 식별명을 만든다."""
    match = re.search(r"\s\d+(?:-\d+)?\s+(.+?)(?:\s+제?\d+층|\s+\d+층)", address)
    if match:
        candidate = clean(match.group(1)).strip(" ,")
        if candidate and candidate != APT:
            return candidate

    parts = address.split()
    district = extract_district(address)
    emd = next((part for part in parts if part.endswith(("동", "읍", "면"))), "")
    if district and emd:
        return f"{district} {emd} {category or APT}"
    return category or extract_complex(address)


def onbid_detail_url(item: dict[str, Any]) -> str:
    params = {
        "cltrScrnGrpCd": str(item.get("cltrScrnGrpCd") or "0001"),
        "cltrPrptDivCd": str(item.get("cltrPrptDivCd") or ""),
        "onbidCltrno": str(item.get("onbidCltrno") or ""),
        "onbidPbancNo": str(item.get("onbidPbancNo") or ""),
        "pbctNo": str(item.get("pbctNo") or ""),
        "pbctCdtnNo": str(item.get("pbctCdtnNo") or ""),
        "rtnListUrl": "/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do",
    }
    return f"{ONBID_DETAIL_URL}?{urlencode(params)}"


def normalize_onbid_status(value: str) -> str:
    value = clean(value)
    if "진행" in value or "입찰중" in value:
        return "입찰중"
    if "준비" in value:
        return "입찰 예정"
    if "마감" in value:
        return "입찰 마감"
    if "유찰" in value:
        return "유찰"
    if "낙찰" in value or "매각" in value:
        return "매각"
    return value or "입찰 예정"


def onbid_row_to_auction(row: dict[str, Any], today: date) -> dict[str, Any] | None:
    category = clean(row.get("ctgrNm"))
    residential_categories = {APT, "\uae30\ud0c0\uc8fc\uac70\uc6a9\uac74\ubb3c"}
    if category not in residential_categories:
        return None

    address = clean(row.get("onbidCltrNm"))
    if not address or not is_in_scope(address):
        return None

    management_no = clean(row.get("scrnIndctCltrMngNo"))
    if not management_no:
        return None

    bid_date = parse_date(
        clean(row.get("pbctLastDdlnDt") or row.get("pbctDdlnDt") or row.get("pbctBegnDtm"))
    )
    status = normalize_onbid_status(row.get("pbancPbctCltrStatNm") or "")
    appraisal = row.get("cltrApslEvlAvgAmt")
    minimum = row.get("lowstBidPrc")
    try:
        appraisal = int(appraisal) if appraisal not in (None, "") else None
    except (TypeError, ValueError):
        appraisal = None
    try:
        minimum = int(minimum) if minimum not in (None, "") else None
    except (TypeError, ValueError):
        minimum = None

    building_m2 = parse_float(row.get("bldSqms"))
    building_pyeong = round(building_m2 / 3.305785, 2) if building_m2 is not None else None
    land_m2 = parse_float(row.get("landSqms"))
    land_pyeong = round(land_m2 / 3.305785, 2) if land_m2 is not None else None
    is_interest = building_pyeong is not None and 24 <= building_pyeong <= 40
    upcoming = bool(
        bid_date
        and date.fromisoformat(bid_date) >= today
        and status not in ("입찰 마감", "유찰", "매각")
    )
    discount = round((1 - minimum / appraisal) * 100, 1) if appraisal and minimum else None
    minimum_ratio = round(minimum / appraisal * 100) if appraisal and minimum else None
    try:
        auction_round = int(str(row.get("pbctNsq") or "").lstrip("0") or "0") or None
    except ValueError:
        auction_round = None

    tags: list[str] = []
    for value in (row.get("scrnPrptDvsnNm"), row.get("dspsMthodNm")):
        tag = clean(value)
        if tag and tag not in tags:
            tags.append(tag)

    official_url = onbid_detail_url(row)
    district = extract_district(address)
    rights_note = (
        f"온비드 재산구분: {clean(row.get('scrnPrptDvsnNm')) or '확인 필요'}, "
        f"처분방식: {clean(row.get('dspsMthodNm')) or '확인 필요'}, "
        f"기관: {clean(row.get('regOrgNm')) or '확인 필요'}. "
        "공고문·감정평가서·현황을 온비드 원문에서 확인하세요."
    )

    return {
        "id": f"onbid:{management_no}:{row.get('pbctCdtnNo') or row.get('pbctNo') or ''}",
        "source_type": "onbid",
        "auction_kind": "온비드 공매",
        "case_no": management_no,
        "case_display": management_no,
        "court": clean(row.get("regOrgNm")) or "한국자산관리공사",
        "category": category,
        "district": district,
        "complex": extract_onbid_complex(address, category),
        "address": address,
        "bid_date": bid_date,
        "status": status,
        "status_raw": clean(row.get("pbancPbctCltrStatNm")),
        "auction_round": auction_round,
        "appraisal": appraisal,
        "minimum_price": minimum,
        "final_price": None,
        "minimum_ratio": minimum_ratio,
        "final_ratio": None,
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
        "risk_tags": tags,
        "school_access": "미확인 — 현장·지도 확인 필요",
        "rights_note": rights_note,
        "area_note": "온비드 건물면적 기준 — 전용면적·공급면적은 온비드 공고 원문에서 최종 확인",
        "source_name": ONBID_SOURCE_NAME,
        "source_kind": ONBID_SOURCE_KIND,
        "source_url": official_url,
        "official_url": official_url,
        "onbid_cltrno": row.get("onbidCltrno"),
        "onbid_pbanc_no": row.get("onbidPbancNo"),
        "pbct_no": row.get("pbctNo"),
        "pbct_cdtn_no": row.get("pbctCdtnNo"),
    }


def collect_onbid(
    session: requests.Session,
    today: date,
    future_days: int,
    page_unit: int = 100,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """온비드 공식 조건검색의 울산 주거용 건물을 조회한다."""
    region = ",".join(f"{ONBID_DISTRICT_PREFIX}>{district}" for district in ALLOWED_DISTRICTS)
    params: dict[str, Any] = {
        "pageIndex": "1",
        "pageUnit": str(page_unit),
        "searchCltrMnmtNoYn": "N",
        "srchCltrType": "0001",
        "srchPrptType": "",
        "srchDspsMthod": "",
        "srchBidPerdBgngDt": today.isoformat(),
        "srchBidPerdEndDt": (today + timedelta(days=max(30, future_days))).isoformat(),
        "srchBidPerdType": "0004",
        "srchArrayCtgrId": ONBID_CATEGORY_ID,
        "srchArrayRgn": region,
        "srchSortType": "DESC",
        "srchWordType": "",
        "srchPvctYn": "N",
        "srchBidMthod": "",
        "srchApslEvlAmtType": "",
        "srchLowstBidBgng": "",
        "rtnListUrl": ONBID_SEARCH_URL,
        "srchPbancStatSrchPvctYn": "N",
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ONBID_SEARCH_URL,
    }
    response = session.post(ONBID_LIST_URL, data=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError("온비드 공식 검색 응답이 성공 상태가 아닙니다.")

    rows = payload.get("cltrInfVOList") or []
    pagination = payload.get("paginationInfo") or {}
    total_pages = min(int(pagination.get("totalPageCount") or 1), 20)
    source_urls = [ONBID_SEARCH_URL, response.url]

    for page in range(2, total_pages + 1):
        params["pageIndex"] = str(page)
        page_response = session.post(ONBID_LIST_URL, data=params, headers=headers, timeout=30)
        page_response.raise_for_status()
        page_payload = page_response.json()
        rows.extend(page_payload.get("cltrInfVOList") or [])
        source_urls.append(page_response.url)

    records = [item for row in rows if (item := onbid_row_to_auction(row, today))]
    return records, source_urls, []


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
        "source_type": "court",
        "auction_kind": "법원경매",
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

    try:
        onbid_items, onbid_urls, onbid_errors = collect_onbid(
            session,
            today,
            future_days=max(90, args.history_days),
        )
        items.extend(onbid_items)
        search_urls.extend(onbid_urls)
        errors.extend(onbid_errors)
        print(f"  \uc628\ube44\ub4dc \uacf5\ub9e4 \ubaa9\ub85d: {len(onbid_items)}\uac74")
    except Exception as exc:
        errors.append(f"\uc628\ube44\ub4dc \uacf5\ub9e4 \ubaa9\ub85d: {exc}")
        print(f"  \uc628\ube44\ub4dc \uacf5\ub9e4 \ubaa9\ub85d \uc2e4\ud328: {exc}")

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
            "onbid": {"name": ONBID_SOURCE_NAME, "kind": ONBID_SOURCE_KIND, "url": ONBID_SEARCH_URL},
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
