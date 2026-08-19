# 울산 아파트 경매 모아보기

울산지방법원 관할 공개 경매목록에서 아파트 물건을 모아, 입찰일·감정가·최저가·상태를 한 화면에서 검색하는 정적 사이트입니다.

## 기본 감시 범위

- 포함: 울산 중구·남구·북구(송정동 포함)
- 제외: 동구·울주군
- 관심 면적: 공개목록의 건물 24~40평
- 우선 조건: 공급 32평 이상, 초등학교 실제 도보 10분 이내, 500세대 이상 대단지

공개목록에는 전용면적·공급면적·학교·세대수·권리·임차인 정보가 모두 제공되지 않을 수 있습니다. 따라서 사이트는 확인되지 않은 내용을 추정하지 않고 `확인 필요`로 표시합니다.

## 실행

```powershell
cd C:\workspace\NaverBlog\ulsanapt
python -m pip install -r requirements.txt
python collect.py
python build_site.py
```

생성 결과는 `site/index.html`과 `docs/index.html`입니다. `docs` 폴더를 GitHub Pages의 배포 폴더로 사용할 수 있습니다.

최근 일정목록을 더 넓게 확인하려면:

```powershell
python collect.py --history-days 120 --delay 0.08
python build_site.py
```

## 데이터 출처와 주의사항

- 최종 확인: [대한민국 법원경매정보](https://www.courtauction.go.kr/)
- 수집 보조: [위너옥션 공개 검색목록](https://www.winnerauction.co.kr/search/search_list.php?acourt=411&acharge=10&usage_codes=101)

공개 검색목록은 보조 자료입니다. 입찰 전 사건 상세, 매각물건명세서, 현황조사서, 등기사항증명서와 현장을 직접 확인해야 합니다.

최근 실거래가 대비 할인율은 단지명·면적 매칭 오류를 피하기 위해 현재 자동 확정하지 않습니다. 상세 화면에는 연동 대기 상태를 표시하고, 최종 확인은 [국토교통부 실거래가 공개시스템](https://rt.molit.go.kr/pt/gis/gis.do?mobileAt=&srhThingSecd=C)에서 하도록 구성했습니다.
