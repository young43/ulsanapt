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
OFFICIAL_SEARCH_URL = "https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on"
OFFICIAL_DETAIL_URL = "https://www.courtauction.go.kr/pgj/pgj15B/selectAuctnCsSrchRslt.on"
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
OFFICIAL_COURT = "B000411"  # 대한민국 법원경매정보의 울산지방법원 코드
OFFICIAL_APT_LCL = "20000"
OFFICIAL_APT_MCL = "20100"
OFFICIAL_APT_SCL = "20104"
OFFICIAL_WINDOW_DAYS = 14  # 공식 상세검색이 허용하는 미래 매각기일 범위
ALLOWED_DISTRICTS = ("중구", "남구", "북구")
EXCLUDED_DISTRICTS = ("동구", "울주군")
STATUS_WORDS = ("매각", "유찰", "변경", "취하", "진행", "신건")
MONEY_RE = re.compile(r"\d[\d,]*")
DATE_RE = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")
COMPACT_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")
AREA_M2_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:㎡|m²|m2)", re.IGNORECASE)

OFFICIAL_SEARCH_INFO_KEYS = (
    "rletDspslSpcCondCd", "rprsAdongSdCd", "rprsAdongSggCd", "rprsAdongEmdCd",
    "rdnmSdCd", "rdnmSggCd", "rdnmNo", "mvprpDspslPlcAdongSdCd",
    "mvprpDspslPlcAdongSggCd", "mvprpDspslPlcAdongEmdCd", "rdDspslPlcAdongSdCd",
    "rdDspslPlcAdongSggCd", "rdDspslPlcAdongEmdCd", "jdbnCd", "execrOfcDvsCd",
    "lclDspslGdsLstUsgCd", "mclDspslGdsLstUsgCd", "sclDspslGdsLstUsgCd",
    "cortAuctnMbrsId", "aeeEvlAmtMin", "aeeEvlAmtMax", "lwsDspslPrcRateMin",
    "lwsDspslPrcRateMax", "flbdNcntMin", "flbdNcntMax", "objctArDtsMin",
    "objctArDtsMax", "mvprpArtclKndCd", "mvprpArtclNm", "mvprpAtchmPlcTypCd",
    "lafjOrderBy", "csNo", "dspslDxdyYmd", "fstDspslHm", "scndDspslHm",
    "thrdDspslHm", "fothDspslHm", "dspslPlcNm", "lwsDspslPrcMin",
    "lwsDspslPrcMax", "grbxTypCd", "gdsVendNm", "fuelKndCd", "carMdyrMax",
    "carMdyrMin", "carMdlNm", "sideDvsCd",
)


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
        match = COMPACT_DATE_RE.search(value or "")
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


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_area_m2(value: Any) -> float | None:
    matches = AREA_M2_RE.findall(clean(str(value or "")))
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def normalize_case_no(value: Any) -> str:
    """법원 사이트별 사건번호 표기를 하나의 키로 맞춘다."""
    text = clean(str(value or ""))
    match = re.search(r"(20\d{2})\s*(?:타경|타|타기|타채)\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2))}"
    match = re.search(r"(20\d{2})\s*[- ]\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2))}"
    return text


def address_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", clean(value)).lower()


def court_tracking_key(case_no: str, address: str) -> str:
    return f"court:{normalize_case_no(case_no)}:{address_key(address)}"


def auction_event(item: dict[str, Any]) -> dict[str, Any] | None:
    bid_date = item.get("bid_date")
    if not bid_date:
        return None
    return {
        "bid_date": bid_date,
        "status": item.get("status") or "확인 필요",
        "minimum_price": item.get("minimum_price"),
        "minimum_ratio": item.get("minimum_ratio"),
        "auction_round": item.get("auction_round"),
    }


def annotate_risk_profile(item: dict[str, Any]) -> dict[str, Any]:
    """초보자가 확인할 권리·임차인·점유 체크 항목을 보수적으로 붙인다."""
    for key, default in (
        ("case_type", ""),
        ("claim_amount", None),
        ("case_received_date", ""),
        ("case_command_date", ""),
        ("rights_reference", ""),
        ("special_notes", ""),
    ):
        item.setdefault(key, default)
    text = " ".join(
        str(item.get(key) or "")
        for key in (
            "rights_note",
            "special_notes",
            "rights_reference",
            "status_raw",
            "risk_tags",
        )
    )
    tenant_terms = (
        "임차인",
        "임대차",
        "주택임차권",
        "임차권등기",
        "전세권",
        "보증금",
        "대항력",
        "배당요구",
        "확정일자",
    )
    rights_terms = (
        "근저당",
        "저당권",
        "압류",
        "가압류",
        "가처분",
        "경매개시",
        "유치권",
        "법정지상권",
        "토지별도등기",
        "제시외",
    )
    tenant_text = text.replace("매수신청보증금", "")
    tenant_evidence = [term for term in tenant_terms if term in tenant_text]
    rights_evidence = [term for term in rights_terms if term in text]

    if tenant_evidence:
        tenant_status = "임차권 관련 문구 있음"
        tenant_note = "임차인 존재·보증금 인수 여부가 확정된다는 뜻은 아니며, 공식 서류 대조가 필요합니다."
    elif item.get("source_type") == "onbid":
        tenant_status = "온비드 공개목록만으로 확인 불가"
        tenant_note = "온비드 공고문과 처분기관 자료에서 점유·임대차 조건을 별도로 확인하세요."
    else:
        tenant_status = "공개자료에서 임차인 정보 미확인"
        tenant_note = "임차인이 없다는 뜻이 아닙니다. 매각물건명세서·현황조사서에서 반드시 확인하세요."

    occupancy_terms = [term for term in ("점유", "거주", "명도", "공실") if term in text]
    occupancy_status = (
        "점유 관련 문구 있음 — 현황조사서·현장 재확인"
        if occupancy_terms
        else "실제 점유·공실 여부 확인 필요"
    )

    risk_flags: list[str] = []
    if item.get("is_reauction"):
        risk_flags.append("유찰·재매각 이력")
    if tenant_evidence:
        risk_flags.append("임차권·보증금 문구")
    if rights_evidence:
        risk_flags.append("권리 관련 문구")
    if item.get("source_type") == "onbid":
        risk_flags.append("공매 조건 별도 확인")

    warnings = [
        "임차인 없음으로 단정하지 말고, 매각물건명세서·현황조사서에서 임차인·보증금·전입일·확정일자·배당요구를 확인하세요.",
        "낙찰가 외에 취득세·법무사비·명도비·수리비·체납관리비 등 추가 비용을 예산에 넣으세요.",
        "등기사항증명서에서 말소기준권리와 매각으로 소멸하지 않을 수 있는 권리를 확인하세요.",
    ]
    if tenant_evidence:
        warnings.insert(
            0,
            "임차권 관련 문구가 있습니다. 보증금 인수 여부·전입일·확정일자·배당요구 여부를 확인하기 전에는 입찰하지 마세요.",
        )
    if item.get("is_reauction"):
        warnings.append("유찰·재매각 사유와 매수신청보증금 비율을 이번 회차 공식 공고에서 다시 확인하세요.")
    if item.get("source_type") == "onbid":
        warnings.insert(0, "온비드는 법원경매와 절차·권리 구조가 다를 수 있으므로 온비드 공고문과 처분기관 조건을 우선 확인하세요.")

    checklist = [
        "매각물건명세서: 임차인, 보증금, 전입일, 확정일자, 배당요구, 인수조건",
        "현황조사서: 실제 점유자, 공실 여부, 점유 관계와 현장 상태",
        "등기사항증명서: 말소기준권리, 근저당·압류·가압류·전세권·임차권등기",
        "현장·관리사무소: 누수·수리비·체납관리비·명도 가능성",
    ]
    if item.get("source_type") == "onbid":
        checklist.insert(0, "온비드 공고문: 처분기관, 인도·명도 조건, 체납·보증금·입찰보증금 조건")

    item["tenant_status"] = tenant_status
    item["tenant_evidence"] = tenant_evidence
    item["tenant_note"] = tenant_note
    item["occupancy_status"] = occupancy_status
    item["risk_flags"] = risk_flags
    item["risk_level"] = "주의 필요" if risk_flags else "확인 필요"
    item["beginner_warnings"] = list(dict.fromkeys(warnings))
    item["bid_checklist"] = checklist
    return item


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
        "tracking_key": f"onbid:{management_no}:{row.get('pbctCdtnNo') or row.get('pbctNo') or ''}",
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
        "next_bid_date": bid_date if upcoming else "",
        "last_bid_date": "",
        "status": status,
        "status_raw": clean(row.get("pbancPbctCltrStatNm")),
        "auction_round": auction_round,
        "failed_count": 0,
        "is_failed": False,
        "is_reauction": False,
        "previous_status": "",
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
        "auction_history": [
            event for event in [{
                "bid_date": bid_date,
                "status": status,
                "minimum_price": minimum,
                "minimum_ratio": minimum_ratio,
                "auction_round": auction_round,
            }] if bid_date
        ],
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


def official_search_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.courtauction.go.kr",
        "Referer": "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml",
        "sc-userid": "SYSTEM",
        "submissionid": "mf_wfm_mainFrame_sbm_selectGdsDtlSrch",
    }


def official_search_payload(
    start: date,
    end: date,
    page_no: int,
    page_size: int,
    total_yn: str,
    total_count: str = "",
) -> dict[str, Any]:
    page_info: dict[str, Any] = {
        "pageNo": page_no,
        "pageSize": page_size,
        "bfPageNo": page_no - 1 if page_no > 1 else "",
        "startRowNo": "",
        "totalCnt": total_count,
        "totalYn": total_yn,
        "groupTotalCount": "",
    }
    search_info = {key: "" for key in OFFICIAL_SEARCH_INFO_KEYS}
    search_info.update(
        {
            "bidDvsCd": "000331",  # 부동산
            "mvprpRletDvsCd": "00031R",  # 부동산 상세검색
            "cortAuctnSrchCondCd": "0004601",  # 매각기일 검색
            "cortOfcCd": OFFICIAL_COURT,
            "lclDspslGdsLstUsgCd": OFFICIAL_APT_LCL,
            "mclDspslGdsLstUsgCd": OFFICIAL_APT_MCL,
            "sclDspslGdsLstUsgCd": OFFICIAL_APT_SCL,
            "notifyLoc": "off",
            "pgmId": "PGJ151F01",
            "cortStDvs": "1",
            "statNum": 1,
            "bidBgngYmd": start.strftime("%Y%m%d"),
            "bidEndYmd": end.strftime("%Y%m%d"),
        }
    )
    return {"dma_pageInfo": page_info, "dma_srchGdsDtlSrchInfo": search_info}


def official_detail_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.courtauction.go.kr",
        "Referer": "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml",
        "sc-userid": "NONUSER",
        "sc-pgmid": "PGJ15BM01",
        "submissionid": "mf_wfm_mainFrame_sbm_selectGdsDtlSrchDtlInfo",
    }


def official_detail_payload(item: dict[str, Any], today: date) -> dict[str, Any]:
    search_info = official_search_payload(
        today,
        today + timedelta(days=OFFICIAL_WINDOW_DAYS),
        1,
        40,
        "Y",
    )["dma_srchGdsDtlSrchInfo"]
    search_info.update(
        {
            "sideDvsCd": "2",
            "srchRowIndex": 0,
            "menuNm": "물건상세검색",
        }
    )
    object_seq = clean(
        str(
            item.get("court_object_seq")
            or item.get("court_object_no")
            or "1"
        )
    )
    return {
        "dma_srchGdsDtlSrch": {
            "csNo": item.get("case_display") or item.get("case_no") or "",
            "cortOfcCd": OFFICIAL_COURT,
            "dspslGdsSeq": object_seq,
            "pgmId": "PGJ151M01",
            "srchInfo": search_info,
        }
    }


def official_detail_status(event: dict[str, Any], event_date: str, today: date) -> str:
    result_code = clean(
        str(
            event.get("auctnDxdyRsltCd")
            or event.get("dxdyRsltCd")
            or ""
        )
    )
    result_name = clean(
        str(
            event.get("auctnDxdyRsltNm")
            or event.get("dxdyRsltNm")
            or event.get("auctnDxdyRslt")
            or ""
        )
    )
    if "유찰" in result_name or result_code == "003":
        return "유찰"
    if event_date and event_date >= today.isoformat():
        return "입찰 예정"
    if result_name:
        return result_name
    return "매각기일 경과"


def official_detail_event_price(event: dict[str, Any]) -> int | None:
    for key in (
        "tsLwsDspslPrc",
        "lwsDspslPrc",
        "dspslAmt",
        "fstPbancLwsDspslPrc",
    ):
        value = parse_int(event.get(key))
        if value is not None and value > 0:
            return value
    return None


def apply_official_detail(item: dict[str, Any], result: dict[str, Any], today: date) -> bool:
    dxdy_info = result.get("dspslGdsDxdyInfo") or {}
    raw_events = result.get("gdsDspslDxdyLst") or []
    if isinstance(raw_events, dict):
        raw_events = [raw_events]
    if not isinstance(raw_events, list):
        raw_events = []

    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        event_date = parse_date(str(raw_event.get("dxdyYmd") or raw_event.get("maeGiil") or ""))
        if not event_date:
            continue
        price = official_detail_event_price(raw_event)
        ratio = parse_int(
            raw_event.get("lwsDspslPrcRate")
            or raw_event.get("dspslPrcRate")
            or raw_event.get("notifyMinmaePriceRate1")
        )
        appraisal = parse_int(dxdy_info.get("aeeEvlAmt")) or parse_int(item.get("appraisal"))
        if ratio is None and appraisal and price:
            ratio = round(price / appraisal * 100)
        round_value = parse_int(raw_event.get("auctnDxdyKndCd"))
        events.append(
            {
                "bid_date": event_date,
                "status": official_detail_status(raw_event, event_date, today),
                "minimum_price": price,
                "minimum_ratio": ratio,
                "auction_round": round_value,
            }
        )

    if not events:
        next_date = parse_date(
            str(
                dxdy_info.get("dspslDxdyYmd")
                or dxdy_info.get("dspslDcsnDxdyYmd")
                or ""
            )
        )
        if next_date:
            price = parse_int(dxdy_info.get("fstPbancLwsDspslPrc"))
            appraisal = parse_int(dxdy_info.get("aeeEvlAmt"))
            events.append(
                {
                    "bid_date": next_date,
                    "status": official_detail_status({}, next_date, today),
                    "minimum_price": price,
                    "minimum_ratio": round(price / appraisal * 100) if price and appraisal else None,
                    "auction_round": None,
                }
            )
    if not events:
        return False

    events.sort(key=lambda event: (event.get("bid_date") or "", event.get("auction_round") or 0))
    today_text = today.isoformat()
    future_events = [event for event in events if event.get("bid_date", "") >= today_text]
    auction_dates = {
        parse_date(str(raw_event.get("dxdyYmd") or raw_event.get("maeGiil") or ""))
        for raw_event in raw_events
        if clean(str(raw_event.get("auctnDxdyKndCd") or "")) == "01"
    }
    auction_events = [event for event in events if event.get("bid_date") in auction_dates]
    future_auction_events = [event for event in auction_events if event.get("bid_date", "") >= today_text]
    next_event = min(
        future_auction_events or future_events,
        key=lambda event: event.get("bid_date") or "9999-99-99",
    ) if (future_auction_events or future_events) else None

    explicit_failed = sum(1 for event in events if event.get("status") == "유찰")
    failed_count = max(
        parse_int(item.get("failed_count")) or 0,
        explicit_failed,
        (parse_int(item.get("auction_round")) or 1) - 1,
        parse_int(dxdy_info.get("flbdNcnt")) or 0,
    )
    appraisal = parse_int(dxdy_info.get("aeeEvlAmt")) or item.get("appraisal")
    if appraisal:
        item["appraisal"] = appraisal

    if next_event:
        next_date = next_event.get("bid_date") or ""
        minimum = next_event.get("minimum_price")
        if minimum is None:
            minimum = parse_int(dxdy_info.get("fstPbancLwsDspslPrc")) or item.get("minimum_price")
        item["bid_date"] = next_date
        item["next_bid_date"] = next_date
        item["last_bid_date"] = max(
            (event.get("bid_date") for event in events if event.get("bid_date", "") < next_date),
            default="",
        )
        item["is_upcoming"] = True
        item["status"] = "입찰 예정"
        item["minimum_price"] = minimum
        item["minimum_ratio"] = (
            round(minimum / appraisal * 100) if minimum and appraisal else item.get("minimum_ratio")
        )
        item["discount_vs_appraisal"] = (
            round((1 - minimum / appraisal) * 100, 1) if minimum and appraisal else item.get("discount_vs_appraisal")
        )
        item["auction_round"] = max(failed_count + 1, parse_int(item.get("auction_round")) or 0) or None
    else:
        latest = events[-1]
        item["bid_date"] = latest.get("bid_date") or item.get("bid_date")
        item["next_bid_date"] = ""
        item["last_bid_date"] = latest.get("bid_date") or item.get("last_bid_date")
        item["is_upcoming"] = False
        item["status"] = latest.get("status") or item.get("status")

    base_info = result.get("csBaseInfo") or {}
    special_notes = [
        clean(str(dxdy_info.get("gdsSpcfcRmk") or "")),
        clean(str(dxdy_info.get("dspslGdsRmk") or "")),
        clean(str(dxdy_info.get("ndstrcRghCtt") or "")),
    ]
    special_notes = list(dict.fromkeys(note for note in special_notes if note))
    reauction_marker = item.get("is_reauction") or any("재매각" in note for note in special_notes)
    item["failed_count"] = failed_count
    item["is_failed"] = failed_count > 0
    item["is_reauction"] = failed_count > 0 or reauction_marker
    item["previous_status"] = "유찰" if failed_count else ("재매각" if reauction_marker else item.get("previous_status") or "")
    item["case_type"] = clean(str(base_info.get("csNm") or ""))
    item["claim_amount"] = parse_int(base_info.get("clmAmt"))
    item["case_received_date"] = parse_date(str(base_info.get("csRcptYmd") or ""))
    item["case_command_date"] = parse_date(str(base_info.get("csCmdcYmd") or ""))
    item["rights_reference"] = clean(str(dxdy_info.get("tprtyRnkHypthcStngDts") or ""))
    item["special_notes"] = " / ".join(special_notes)
    if special_notes:
        detail_note = "공식 상세 비고: " + " / ".join(special_notes)
        current_rights_note = clean(str(item.get("rights_note") or ""))
        if detail_note not in current_rights_note:
            item["rights_note"] = f"{current_rights_note} {detail_note}".strip()
    item["source_origin"] = "official_detail"
    item["source_name"] = "대한민국 법원경매정보 공식 상세조회"
    item["source_kind"] = "공식 사건 상세 응답"
    item["source_url"] = OFFICIAL_URL
    item["official_url"] = OFFICIAL_URL
    item["official_detail_url"] = OFFICIAL_DETAIL_URL
    item["auction_history"] = events
    return True


def enrich_official_details(
    session: requests.Session,
    items: list[dict[str, Any]],
    today: date,
    delay: float,
    max_details: int = 20,
) -> tuple[int, list[str], list[str]]:
    """과거 유찰 법원물건의 공식 상세조회에서 다음 회차와 이력을 보강한다."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if item.get("source_type") != "court":
            continue
        if item.get("source_origin") == "official_detail":
            continue
        if not (
            item.get("status") == "유찰"
            or (parse_int(item.get("failed_count")) or 0) > 0
            or (parse_int(item.get("auction_round")) or 1) > 1
            or item.get("is_reauction")
        ):
            continue
        key = item.get("tracking_key") or item.get("case_no") or item.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(item)

    candidates.sort(
        key=lambda item: (
            0 if "재매각" in str(item.get("rights_note") or "") else 1,
            0 if item.get("source_origin") != "official_court" else 1,
            item.get("next_bid_date") or item.get("bid_date") or "9999-99-99",
        )
    )
    candidates = candidates[:max_details]

    if not candidates:
        return 0, [], []

    updated = 0
    source_urls = [OFFICIAL_URL, OFFICIAL_DETAIL_URL]
    errors: list[str] = []
    headers = official_detail_headers()
    for item in candidates:
        case_display = item.get("case_display") or item.get("case_no") or item.get("id")
        try:
            response = session.post(
                OFFICIAL_DETAIL_URL,
                json=official_detail_payload(item, today),
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("errors"):
                raise RuntimeError(str(body["errors"]))
            result = ((body.get("data") or {}).get("dma_result") or {})
            if not result or not apply_official_detail(item, result, today):
                raise RuntimeError("상세조회 결과에 매각기일 이력이 없습니다.")
            updated += 1
        except Exception as exc:
            errors.append(f"{case_display}: {exc}")
        if delay:
            time.sleep(delay)
    return updated, source_urls, errors


def official_row_to_auction(row: dict[str, Any], today: date) -> dict[str, Any] | None:
    category = clean(row.get("dspslUsgNm"))
    if category != APT:
        return None

    address = clean(row.get("printSt") or row.get("convAddr"))
    if address.startswith("[") and address.endswith("]"):
        address = address[1:-1].strip()
    if not address or not is_in_scope(address):
        return None

    case_no = normalize_case_no(row.get("srnSaNo") or row.get("saNo"))
    bid_date = parse_date(str(row.get("maeGiil") or ""))
    if not case_no or not bid_date:
        return None

    failed_count = parse_int(row.get("yuchalCnt")) or 0
    auction_round = failed_count + 1
    upcoming = date.fromisoformat(bid_date) >= today
    appraisal = parse_int(row.get("gamevalAmt"))
    minimum = parse_int(row.get("notifyMinmaePrice1")) or parse_int(row.get("minmaePrice"))
    minimum_ratio = parse_int(row.get("notifyMinmaePriceRate1"))
    if minimum_ratio is None and appraisal and minimum:
        minimum_ratio = round(minimum / appraisal * 100)
    discount = round((1 - minimum / appraisal) * 100, 1) if appraisal and minimum else None

    building_m2 = parse_area_m2(row.get("pjbBuldList"))
    if building_m2 is None:
        building_m2 = parse_float(row.get("minArea"))
    building_pyeong = round(building_m2 / 3.305785, 2) if building_m2 is not None else None
    is_interest = building_pyeong is not None and 24 <= building_pyeong <= 40

    notes = clean(row.get("mulBigo"))
    risk_tags = [f"유찰 {failed_count}회"] if failed_count else []
    reauction_note = "재매각" in notes
    if reauction_note:
        risk_tags.insert(0, "재매각")
    if notes:
        first_note = clean(re.split(r"[\r\n]+", notes)[0])
        if first_note and first_note not in risk_tags:
            risk_tags.append(first_note[:80])
    complex_name = clean(row.get("buldNm")) or extract_complex(address)
    status = "입찰 예정" if upcoming else "입찰 마감"
    tracking_key = court_tracking_key(case_no, address)

    return {
        "id": f"court:{tracking_key}",
        "tracking_key": tracking_key,
        "source_origin": "official_court",
        "source_type": "court",
        "auction_kind": "법원경매",
        "case_no": case_no,
        "case_display": case_no.replace("-", "타경", 1),
        "court": clean(row.get("jiwonNm")) or "울산지방법원",
        "category": category,
        "district": extract_district(address),
        "complex": complex_name,
        "address": address,
        "bid_date": bid_date,
        "next_bid_date": bid_date if upcoming else "",
        "last_bid_date": "",
        "status": status,
        "status_raw": f"유찰 {failed_count}회 후 다음 매각" if failed_count else status,
        "auction_round": auction_round,
        "failed_count": failed_count,
        "is_failed": failed_count > 0,
        "is_reauction": failed_count > 0 or reauction_note,
        "previous_status": "유찰" if failed_count else ("재매각" if reauction_note else ""),
        "appraisal": appraisal,
        "minimum_price": minimum,
        "final_price": None,
        "minimum_ratio": minimum_ratio,
        "final_ratio": None,
        "discount_vs_appraisal": discount,
        "market_price": None,
        "market_discount": None,
        "market_note": "국토교통부 실거래가 자동 매칭 전 — 단지명·면적 확인 후 별도 연동",
        "land_pyeong": None,
        "building_pyeong": building_pyeong,
        "building_m2": building_m2,
        "supply_pyeong": None,
        "is_interest": is_interest,
        "is_upcoming": upcoming,
        "risk_tags": risk_tags,
        "school_access": "미확인 — 현장·지도 확인 필요",
        "rights_note": (
            f"법원 공식목록 비고: {notes}. " if notes else ""
        ) + "공식 사건 상세·매각물건명세서·현황조사서·등기사항증명서를 확인하세요.",
        "area_note": "법원 공식목록 건물면적 기준 — 전용면적·공급면적은 원문에서 최종 확인",
        "source_name": "대한민국 법원경매정보 공식 검색목록",
        "source_kind": "공식 검색 응답",
        "source_url": OFFICIAL_URL,
        "official_url": OFFICIAL_URL,
        "court_docid": clean(row.get("docid")),
        "court_object_no": clean(row.get("maemulSer")),
        "court_object_seq": clean(row.get("mokmulSer")),
        "auction_history": [
            {
                "bid_date": bid_date,
                "status": status,
                "minimum_price": minimum,
                "minimum_ratio": minimum_ratio,
                "auction_round": auction_round,
            }
        ],
    }


def collect_official_court(
    session: requests.Session,
    today: date,
    future_days: int,
    delay: float,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """대한민국 법원경매정보 공식목록에서 울산 아파트의 다음 매각기일을 조회한다."""
    # 공식 화면과 서버가 허용하는 미래 검색 범위가 14일이므로, 매 실행 때
    # '지금부터 14일'을 조회하고 유찰 횟수와 현재 회차를 함께 저장한다.
    end = today + timedelta(days=min(OFFICIAL_WINDOW_DAYS, max(1, future_days)))
    page_size = 40  # 공식 화면에서 제공하는 최대 페이지 크기
    headers = official_search_headers()
    records: list[dict[str, Any]] = []
    source_urls = [OFFICIAL_URL, OFFICIAL_SEARCH_URL]
    errors: list[str] = []

    try:
        session.get(
            OFFICIAL_URL,
            headers={"Referer": OFFICIAL_URL},
            timeout=30,
        ).raise_for_status()
        total_count = ""
        total_pages = 1
        for page_no in range(1, 21):
            payload = official_search_payload(
                today,
                end,
                page_no,
                page_size,
                "Y" if page_no == 1 else "N",
                total_count,
            )
            response = session.post(
                OFFICIAL_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("errors"):
                raise RuntimeError(str(body["errors"]))
            data = body.get("data") or {}
            page_info = data.get("dma_pageInfo") or {}
            rows = data.get("dlt_srchResult") or []
            total_count = str(page_info.get("totalCnt") or total_count or "0")
            total_pages = min(20, max(1, (int(total_count) + page_size - 1) // page_size))
            records.extend(
                item for row in rows if (item := official_row_to_auction(row, today))
            )
            if page_no >= total_pages:
                break
            if delay:
                time.sleep(delay)
    except Exception as exc:
        errors.append(f"법원 공식목록: {exc}")

    return records, source_urls, errors


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
    case_no = normalize_case_no(case_no)

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
    failed_count = max((auction_round or 1) - 1, 1 if status == "유찰" else 0)
    tracking_key = court_tracking_key(case_no, address)

    return {
        "id": f"court:{tracking_key}",
        "tracking_key": tracking_key,
        "source_origin": "winner_public_list",
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
        "next_bid_date": bid_date if upcoming else "",
        "last_bid_date": bid_date if not upcoming else "",
        "status": status,
        "auction_round": auction_round,
        "failed_count": failed_count,
        "is_failed": status == "유찰" or failed_count > 0,
        "is_reauction": status == "유찰" or failed_count > 0,
        "previous_status": "유찰" if failed_count else "",
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
        "auction_history": [
            {
                "bid_date": bid_date,
                "status": status,
                "minimum_price": minimum,
                "minimum_ratio": minimum_ratio,
                "auction_round": auction_round,
            }
        ] if bid_date else [],
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


def merge_auction_group(group: list[dict[str, Any]], today: date) -> dict[str, Any]:
    def source_rank(item: dict[str, Any]) -> int:
        return 1 if item.get("source_origin") in {"official_court", "official_detail"} else 0

    upcoming_items = [
        item for item in group
        if item.get("is_upcoming") and (item.get("next_bid_date") or item.get("bid_date"))
    ]
    if upcoming_items:
        primary = min(
            upcoming_items,
            key=lambda item: (
                item.get("next_bid_date") or item.get("bid_date") or "9999-99-99",
                -source_rank(item),
            ),
        )
    else:
        primary = max(
            group,
            key=lambda item: (
                item.get("bid_date") or "",
                source_rank(item),
            ),
        )

    merged = dict(primary)
    for item in group:
        for field, value in item.items():
            if field in {"auction_history", "risk_tags"}:
                continue
            if merged.get(field) in (None, "", []):
                merged[field] = value

    history: list[dict[str, Any]] = []
    for item in group:
        events = item.get("auction_history") or []
        if not events:
            event = auction_event(item)
            events = [event] if event else []
        for event in events:
            if not event or not event.get("bid_date"):
                continue
            normalized = {
                "bid_date": event.get("bid_date"),
                "status": event.get("status") or "확인 필요",
                "minimum_price": event.get("minimum_price"),
                "minimum_ratio": event.get("minimum_ratio"),
                "auction_round": event.get("auction_round"),
            }
            if normalized not in history:
                history.append(normalized)
    history.sort(key=lambda event: (event.get("bid_date") or "", event.get("auction_round") or 0))

    future_dates = sorted(
        {
            value
            for item in group
            for value in (item.get("next_bid_date"),)
            if value and value >= today.isoformat()
        }
    )
    next_bid_date = future_dates[0] if future_dates else ""
    history_dates = [event["bid_date"] for event in history if event.get("bid_date")]
    past_dates = [value for value in history_dates if not next_bid_date or value < next_bid_date]
    latest_date = max(history_dates) if history_dates else (merged.get("bid_date") or "")
    last_bid_date = max(past_dates) if past_dates else (latest_date if not next_bid_date else "")

    explicit_failed = sum(1 for event in history if event.get("status") == "유찰")
    failed_count = max(
        [
            parse_int(item.get("failed_count")) or 0
            for item in group
        ]
        + [
            max((parse_int(item.get("auction_round")) or 1) - 1, 0)
            for item in group
        ]
        + [explicit_failed],
    )
    current_item = primary
    has_reauction_marker = any(
        item.get("is_reauction")
        or "재매각" in str(item.get("rights_note") or "")
        for item in group
    )
    merged["id"] = merged.get("tracking_key") or primary.get("id")
    merged["bid_date"] = next_bid_date or latest_date
    merged["next_bid_date"] = next_bid_date
    merged["last_bid_date"] = last_bid_date
    merged["auction_history"] = history
    merged["failed_count"] = failed_count
    merged["is_failed"] = failed_count > 0 or explicit_failed > 0
    merged["is_reauction"] = merged["is_failed"] or has_reauction_marker
    merged["previous_status"] = (
        "유찰" if merged["is_failed"] else ("재매각" if has_reauction_marker else "")
    )
    merged["is_upcoming"] = bool(
        next_bid_date
        and next_bid_date >= today.isoformat()
        and current_item.get("status") not in ("매각", "취하", "입찰 마감")
    )
    if merged["is_upcoming"]:
        merged["status"] = current_item.get("status") or "입찰 예정"
        merged["auction_round"] = failed_count + 1 if failed_count else current_item.get("auction_round")
    elif history:
        merged["status"] = history[-1].get("status") or current_item.get("status") or "확인 필요"
        merged["auction_round"] = history[-1].get("auction_round") or current_item.get("auction_round")
    merged["is_interest"] = any(bool(item.get("is_interest")) for item in group)
    merged["risk_tags"] = list(
        dict.fromkeys(
            tag
            for item in group
            for tag in (item.get("risk_tags") or [])
            if tag
        )
    )
    if failed_count > 0 and f"유찰 {failed_count}회" not in merged["risk_tags"]:
        merged["risk_tags"].insert(0, f"유찰 {failed_count}회")
    return annotate_risk_profile(merged)


def deduplicate(items: list[dict[str, Any]], today: date | None = None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        key = item.get("tracking_key") or item["id"]
        groups.setdefault(key, []).append(item)
    merged = [merge_auction_group(group, today or date.today()) for group in groups.values()]
    return sorted(
        merged,
        key=lambda item: (
            0 if item.get("next_bid_date") else 1,
            item.get("next_bid_date") or item.get("bid_date") or "9999-99-99",
            item.get("case_no") or "",
        ),
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
    official_urls: list[str] = []
    try:
        official_items, official_urls, official_errors = collect_official_court(
            session,
            today,
            future_days=max(1, args.history_days),
            delay=args.delay,
        )
        items.extend(official_items)
        errors.extend(official_errors)
        print(f"  법원 공식 아파트 목록: {len(official_items)}건")
    except Exception as exc:
        errors.append(f"법원 공식 아파트 목록: {exc}")
        print(f"  법원 공식 아파트 목록 실패: {exc}")

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

    detail_count, detail_urls, detail_errors = enrich_official_details(
        session,
        items,
        today,
        delay=args.delay,
    )
    official_urls.extend(detail_urls)
    errors.extend(detail_errors)
    if detail_count or detail_errors:
        print(f"  법원 공식 상세조회 보강: {detail_count}건")

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

    auctions = deduplicate(items, today)
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
            "official_future_window_days": OFFICIAL_WINDOW_DAYS,
        },
        "sources": {
            "onbid": {"name": ONBID_SOURCE_NAME, "kind": ONBID_SOURCE_KIND, "url": ONBID_SEARCH_URL},
            "official": {"name": "대한민국 법원경매정보", "url": OFFICIAL_URL},
            "official_search": {
                "name": "대한민국 법원경매정보 공식 검색목록",
                "kind": "공식 검색 응답",
                "url": OFFICIAL_SEARCH_URL,
            },
            "official_detail": {
                "name": "대한민국 법원경매정보 공식 사건 상세조회",
                "kind": "공식 상세 응답",
                "url": OFFICIAL_DETAIL_URL,
            },
            "public_list": {"name": SOURCE_NAME, "kind": SOURCE_KIND, "url": SEARCH_URL},
            "market": {"name": "국토교통부 실거래가 공개시스템", "url": MARKET_URL},
        },
        "source_urls": list(dict.fromkeys(official_urls + search_urls + history_urls))[:200],
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
