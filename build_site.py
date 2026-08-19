# -*- coding: utf-8 -*-
"""data/auctions.json을 검색 가능한 단일 HTML 사이트로 만든다."""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "auctions.json"
SITE = HERE / "site"
DOCS = HERE / "docs"


CSS = r"""
*, *::before, *::after { box-sizing: border-box; }

:root {
  --bg: #f7f3ed;
  --paper: #fffdf9;
  --paper-2: #f2ece3;
  --ink: #1c2b35;
  --muted: #68757b;
  --faint: #98a09e;
  --line: #e5ddd2;
  --line-strong: #d5cabb;
  --navy: #274750;
  --navy-deep: #19333c;
  --terracotta: #b86b35;
  --terracotta-deep: #954d22;
  --amber: #d99a3e;
  --green: #2d7967;
  --green-bg: #e0f0eb;
  --blue: #4c6e91;
  --blue-bg: #e3ebf4;
  --red: #b34d42;
  --red-bg: #f6e5e1;
  --violet: #756493;
  --violet-bg: #eee9f6;
  --shadow: 0 12px 32px rgba(65, 45, 27, .07), 0 2px 4px rgba(65, 45, 27, .04);
  --radius: 16px;
}

html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at 8% -10%, rgba(216, 164, 99, .15), transparent 31rem),
    var(--bg);
  color: var(--ink);
  font-family: "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont,
    "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
button, input, select { font: inherit; }
button, select { cursor: pointer; }
a { color: inherit; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible,
summary:focus-visible { outline: 3px solid rgba(184, 107, 53, .42); outline-offset: 3px; }

.shell { max-width: 1200px; margin: 0 auto; padding: 0 22px 80px; }
.topbar {
  min-height: 78px; display: flex; align-items: center; justify-content: space-between;
  gap: 18px; border-bottom: 1px solid var(--line);
}
.brand { display: inline-flex; align-items: center; gap: 11px; text-decoration: none; }
.brand-mark {
  width: 34px; height: 34px; display: grid; place-items: center; border-radius: 11px;
  background: var(--navy); color: #f9ede0; font-size: 18px; font-weight: 800;
  box-shadow: 0 5px 13px rgba(39, 71, 80, .17);
}
.brand-name { font-size: 15px; font-weight: 800; letter-spacing: -.02em; }
.brand-sub { color: var(--muted); font-size: 12px; margin-left: 2px; }
.top-link {
  color: var(--muted); font-size: 12px; text-decoration: none; border-bottom: 1px solid transparent;
}
.top-link:hover { color: var(--terracotta-deep); border-color: currentColor; }

.hero { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(310px, .65fr); gap: 20px; padding: 42px 0 24px; }
.hero-copy { padding: 10px 0; }
.eyebrow {
  margin: 0 0 13px; color: var(--terracotta-deep); font-size: 11px; font-weight: 800;
  letter-spacing: .17em; text-transform: uppercase;
}
h1 { margin: 0; max-width: 760px; font-size: clamp(31px, 4vw, 52px); letter-spacing: -.055em; line-height: 1.12; text-wrap: balance; }
.hero-lede { max-width: 650px; margin: 18px 0 0; color: var(--muted); font-size: 16px; line-height: 1.75; }
.hero-lede strong { color: var(--ink); font-weight: 700; }
.hero-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }
.meta-pill {
  border: 1px solid var(--line-strong); background: rgba(255,253,249,.68); border-radius: 999px;
  padding: 5px 11px; color: var(--muted); font-size: 12px;
}
.meta-pill b { color: var(--navy); }
.criteria-card {
  position: relative; overflow: hidden; border-radius: var(--radius); padding: 25px 25px 22px;
  background: var(--navy); color: #f8f0e6; box-shadow: 0 16px 30px rgba(39, 71, 80, .17);
}
.criteria-card::after {
  content: ""; position: absolute; width: 190px; height: 190px; right: -72px; bottom: -88px;
  border: 1px solid rgba(255,255,255,.15); border-radius: 50%; box-shadow: 0 0 0 18px rgba(255,255,255,.04), 0 0 0 36px rgba(255,255,255,.025);
}
.criteria-label { margin: 0 0 8px; color: #e2ad76; font-size: 11px; font-weight: 800; letter-spacing: .13em; }
.criteria-card h2 { margin: 0; font-size: 21px; letter-spacing: -.04em; }
.criteria-list { position: relative; z-index: 1; display: grid; gap: 11px; margin: 20px 0 0; padding: 0; list-style: none; color: #d9e3e2; font-size: 13px; }
.criteria-list li { display: flex; gap: 9px; align-items: flex-start; }
.criteria-list li::before { content: "✓"; color: #e2ad76; font-weight: 800; }
.criteria-foot { position: relative; z-index: 1; margin: 19px 0 0; padding-top: 15px; border-top: 1px solid rgba(255,255,255,.14); color: #afc0c0; font-size: 11.5px; }

.stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 12px 0 26px; }
.stat { min-height: 112px; padding: 18px 18px 16px; background: rgba(255,253,249,.86); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); }
.stat-label { display: block; color: var(--muted); font-size: 12px; }
.stat-value { display: block; margin-top: 8px; color: var(--navy); font-size: 28px; font-weight: 800; letter-spacing: -.06em; line-height: 1; font-variant-numeric: tabular-nums; }
.stat-value.accent { color: var(--terracotta-deep); }
.stat-value.green { color: var(--green); }
.stat-note { display: block; margin-top: 8px; color: var(--faint); font-size: 11px; }

.notice {
  display: flex; gap: 12px; align-items: flex-start; margin: 0 0 18px; padding: 13px 15px;
  border: 1px solid #ead3b8; border-radius: 12px; background: #fff7ec; color: #76553b; font-size: 12.5px;
}
.notice-icon { flex: 0 0 auto; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: #edc28e; color: #70441d; font-weight: 800; }
.notice p { margin: 0; }

.filters-wrap { position: sticky; top: 0; z-index: 20; margin: 0 -22px; padding: 11px 22px 13px; background: rgba(247,243,237,.94); border-bottom: 1px solid var(--line); backdrop-filter: blur(12px); }
.filters { display: grid; gap: 10px; }
.search-row { display: flex; gap: 9px; align-items: center; }
.search-box { position: relative; flex: 1 1 420px; }
.search-box::before { content: "⌕"; position: absolute; left: 13px; top: 6px; color: var(--faint); font-size: 22px; line-height: 1; }
.search-box input { width: 100%; padding-left: 37px; }
input[type="search"], select {
  min-height: 42px; border: 1px solid var(--line-strong); border-radius: 10px; color: var(--ink); background: var(--paper); padding: 8px 12px; font-size: 13px;
}
input[type="search"]::placeholder { color: #a5aaa6; }
select { min-width: 142px; }
.filter-row { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
.filter-label { margin-right: 2px; color: var(--faint); font-size: 11px; font-weight: 800; letter-spacing: .04em; }
.pill {
  display: inline-flex; align-items: center; gap: 6px; min-height: 31px; border: 1px solid var(--line-strong); border-radius: 999px; padding: 4px 11px;
  color: var(--muted); background: var(--paper); font-size: 12px; transition: .15s ease;
}
.pill:hover { border-color: var(--terracotta); color: var(--terracotta-deep); }
.pill[aria-pressed="true"] { border-color: var(--navy); background: var(--navy); color: #fffaf4; }
.pill .count { opacity: .72; font-size: 11px; font-variant-numeric: tabular-nums; }
.filter-divider { width: 1px; height: 20px; margin: 0 4px; background: var(--line-strong); }
.reset-btn { margin-left: auto; border: 0; padding: 5px 4px; color: var(--muted); background: transparent; font-size: 12px; text-decoration: underline; text-underline-offset: 3px; }
.reset-btn:hover { color: var(--terracotta-deep); }
.results-bar { display: flex; align-items: baseline; gap: 8px; margin: 20px 0 10px; }
.results-bar h2 { margin: 0; font-size: 18px; letter-spacing: -.03em; }
.results-bar .result-count { color: var(--muted); font-size: 12px; }
.results-bar .sorter { margin-left: auto; }
.sorter select { min-height: 34px; padding: 5px 9px; font-size: 12px; }

.auction-list { display: grid; gap: 11px; margin: 0; padding: 0; list-style: none; }
.auction-card { position: relative; overflow: hidden; padding: 20px 21px 16px; background: var(--paper); border: 1px solid var(--line); border-radius: 15px; box-shadow: 0 4px 18px rgba(65,45,27,.04); transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease; }
.auction-card::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--line-strong); }
.auction-card.interest::before { background: var(--terracotta); }
.auction-card.upcoming::before { background: var(--green); }
.auction-card:hover { transform: translateY(-1px); border-color: #d5c0a7; box-shadow: var(--shadow); }
.card-head { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 16px; align-items: start; }
.card-kicker { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; color: var(--muted); font-size: 11.5px; }
.status-badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; }
.source-badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; }
.source-badge.source-court { color: var(--navy); background: #e7eef0; }
.source-badge.source-onbid { color: #7b4c20; background: #f6e8d1; }
.status-badge.status-sale { color: var(--blue); background: var(--blue-bg); }
.status-badge.status-fail { color: var(--red); background: var(--red-bg); }
.status-badge.status-change { color: var(--violet); background: var(--violet-bg); }
.status-badge.status-withdraw { color: #727979; background: #eceeed; }
.status-badge.status-open { color: var(--green); background: var(--green-bg); }
.interest-label { color: var(--terracotta-deep); font-weight: 800; }
.card-title { margin: 8px 0 4px; font-size: 18px; line-height: 1.35; letter-spacing: -.035em; }
.card-title a { text-decoration: none; }
.card-title a:hover { color: var(--terracotta-deep); text-decoration: underline; text-underline-offset: 4px; }
.card-address { margin: 0; color: var(--muted); font-size: 12.5px; }
.bid-date { min-width: 115px; text-align: right; color: var(--muted); font-size: 11px; }
.bid-date strong { display: block; margin-top: 2px; color: var(--ink); font-size: 15px; font-variant-numeric: tabular-nums; }
.dday { display: inline-block; margin-top: 3px; color: var(--green); font-size: 11px; font-weight: 800; }
.dday.past { color: var(--faint); font-weight: 600; }
.dday.soon { color: var(--terracotta-deep); }

.metrics { display: grid; grid-template-columns: 1.2fr 1fr 1fr 1fr; gap: 8px; margin-top: 17px; padding: 12px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.metric { min-width: 0; padding: 0 10px; border-left: 1px solid var(--line); }
.metric:first-child { padding-left: 0; border-left: 0; }
.metric-label { display: block; color: var(--faint); font-size: 11px; }
.metric-value { display: block; margin-top: 3px; color: var(--ink); font-size: 14px; font-weight: 800; letter-spacing: -.02em; white-space: nowrap; }
.metric-value small { color: var(--muted); font-size: 11px; font-weight: 500; }
.metric-value em { margin-left: 5px; color: var(--terracotta-deep); font-size: 11px; font-style: normal; font-weight: 800; }
.card-foot { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; padding-top: 12px; color: var(--muted); font-size: 11.5px; }
.card-foot span { display: inline-flex; gap: 4px; align-items: center; }
.card-foot .case { color: var(--navy); font-weight: 700; }
.tag { padding: 2px 7px; border-radius: 5px; background: var(--paper-2); color: #785d43; }
.card-actions { margin-left: auto; display: inline-flex; gap: 8px; }
.text-btn { border: 0; padding: 0; color: var(--terracotta-deep); background: transparent; font-size: 11.5px; font-weight: 800; text-decoration: underline; text-underline-offset: 3px; }
.text-btn:hover { color: var(--navy); }
.empty { padding: 56px 20px; text-align: center; border: 1px dashed var(--line-strong); border-radius: 14px; color: var(--muted); background: rgba(255,253,249,.5); }
.empty strong { display: block; margin-bottom: 5px; color: var(--ink); font-size: 16px; }
.more { display: flex; justify-content: center; margin-top: 16px; }
.more button { border: 1px solid var(--line-strong); border-radius: 9px; padding: 9px 18px; color: var(--ink); background: var(--paper); font-size: 13px; }
.more button:hover { border-color: var(--terracotta); color: var(--terracotta-deep); }

.lower-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 50px; }
.info-panel { padding: 21px; border: 1px solid var(--line); border-radius: 15px; background: rgba(255,253,249,.64); }
.info-panel h2 { margin: 0; font-size: 17px; letter-spacing: -.03em; }
.info-panel > p { margin: 7px 0 16px; color: var(--muted); font-size: 12.5px; }
.info-list { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.info-list li { display: flex; justify-content: space-between; gap: 14px; padding: 9px 0; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 12px; }
.info-list li:last-child { border-bottom: 0; }
.info-list b { color: var(--ink); text-align: right; font-weight: 700; }
.source-link { color: var(--terracotta-deep); font-weight: 700; text-decoration: none; }
.source-link:hover { text-decoration: underline; text-underline-offset: 3px; }
.footer { margin-top: 28px; color: var(--faint); font-size: 11.5px; line-height: 1.8; }
.footer a { color: var(--muted); }
.footer code { color: var(--muted); }

dialog { width: min(680px, calc(100vw - 28px)); max-height: min(760px, calc(100vh - 28px)); padding: 0; border: 0; border-radius: 17px; color: var(--ink); background: var(--paper); box-shadow: 0 30px 80px rgba(20,35,38,.25); }
dialog::backdrop { background: rgba(24, 40, 44, .45); backdrop-filter: blur(3px); }
.dialog-inner { padding: 24px; }
.dialog-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 17px; border-bottom: 1px solid var(--line); }
.dialog-head h2 { margin: 7px 0 4px; font-size: 22px; letter-spacing: -.04em; line-height: 1.3; }
.dialog-head p { margin: 0; color: var(--muted); font-size: 12.5px; }
.close-dialog { width: 30px; height: 30px; border: 1px solid var(--line-strong); border-radius: 50%; color: var(--muted); background: transparent; font-size: 18px; line-height: 1; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 18px; }
.detail-item { padding: 11px 12px; border-radius: 10px; background: var(--paper-2); }
.detail-item span { display: block; color: var(--muted); font-size: 11px; }
.detail-item strong { display: block; margin-top: 3px; font-size: 14px; }
.detail-section { margin-top: 18px; }
.detail-section h3 { margin: 0 0 6px; font-size: 13px; }
.detail-section p { margin: 0; color: var(--muted); font-size: 12.5px; }
.dialog-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line); }
.dialog-actions a { display: inline-flex; align-items: center; min-height: 36px; padding: 7px 12px; border-radius: 8px; color: #fffaf4; background: var(--navy); font-size: 12px; font-weight: 700; text-decoration: none; }
.dialog-actions a.secondary { color: var(--navy); background: var(--paper-2); }

@media (max-width: 820px) {
  .hero { grid-template-columns: 1fr; }
  .criteria-card { max-width: none; }
  .stats { grid-template-columns: repeat(2, 1fr); }
  .metrics { grid-template-columns: repeat(2, 1fr); gap: 12px 0; }
  .metric:nth-child(3) { border-left: 0; padding-left: 0; }
  .metric:nth-child(3), .metric:nth-child(4) { padding-top: 8px; border-top: 1px solid var(--line); }
  .lower-grid { grid-template-columns: 1fr; }
  .filters-wrap { position: static; top: auto; z-index: auto; backdrop-filter: none; }
}
@media (max-width: 620px) {
  .shell { padding-right: 14px; padding-left: 14px; }
  .topbar { min-height: 66px; }
  .brand-sub, .top-link { display: none; }
  .hero { padding-top: 28px; }
  h1 { font-size: 34px; }
  .hero-lede { font-size: 14px; }
  .filters-wrap { margin-right: -14px; margin-left: -14px; padding-right: 14px; padding-left: 14px; }
  .search-row { align-items: stretch; flex-wrap: wrap; }
  .search-box { flex-basis: 100%; }
  .search-row select { flex: 1 1 140px; }
  .results-bar { align-items: flex-start; flex-wrap: wrap; }
  .results-bar .sorter { width: 100%; margin-left: 0; }
  .sorter select { width: 100%; }
  .card-head { grid-template-columns: 1fr; gap: 8px; }
  .bid-date { text-align: left; }
  .bid-date strong { display: inline; margin-right: 7px; }
  .card-title { font-size: 17px; }
  .card-actions { width: 100%; margin-left: 0; }
  .detail-grid { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; } }
"""


JS = r"""
const RAW = window.__AUCTIONS__ || { auctions: [] };
const auctions = Array.isArray(RAW.auctions) ? RAW.auctions : [];
const today = new Date(); today.setHours(0, 0, 0, 0);
const state = { q: "", district: "", status: "", source: "", interest: false, upcoming: false, failedOnly: false, sort: "next_bid_date", limit: 30 };
const $ = (selector) => document.querySelector(selector);
const listEl = $("#auctionList");

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}
function money(value) {
  if (value == null || value === "") return "확인 필요";
  const n = Number(value);
  if (n >= 100000000) {
    const eok = Math.floor(n / 100000000);
    const man = Math.floor((n % 100000000) / 10000);
    return man ? `${eok}억 ${man.toLocaleString("ko-KR")}만` : `${eok}억`;
  }
  return `${Math.round(n / 10000).toLocaleString("ko-KR")}만`;
}
function fullWon(value) { return value == null ? "확인 필요" : `${Number(value).toLocaleString("ko-KR")}원`; }
function dateLabel(value) { return value ? value.replaceAll("-", ".") : "미정"; }
function dayDiff(value) {
  if (!value) return null;
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : Math.round((d - today) / 86400000);
}
function statusClass(status) {
  return ({ "매각":"status-sale", "유찰":"status-fail", "유찰 후 재매각":"status-fail", "변경":"status-change", "취하":"status-withdraw", "진행":"status-open", "신건":"status-open", "입찰 예정":"status-open", "입찰중":"status-open", "입찰 마감":"status-change" }[status] || "status-change");
}
function statusLabel(item) {
  return item.is_reauction ? "유찰 후 재매각" : (item.status || "확인 필요");
}
function sourceLabel(item) {
  return item.source_type === "onbid" ? "\uc628\ube44\ub4dc \uacf5\ub9e4" : "\ubc95\uc6d0\uacbd\ub9e4";
}
function sourceClass(item) {
  return item.source_type === "onbid" ? "source-onbid" : "source-court";
}
function originalLabel(item) {
  return item.source_type === "onbid" ? "\uc628\ube44\ub4dc \uc6d0\ubb38" : "\ubc95\uc6d0 \uc6d0\ubb38";
}
function ddayHtml(item) {
  const date = item.next_bid_date || item.bid_date;
  const diff = dayDiff(date);
  if (item.is_upcoming && diff != null) {
    if (diff === 0) return '<span class="dday soon">오늘 입찰</span>';
    return `<span class="dday${diff <= 7 ? " soon" : ""}">D-${diff}</span>`;
  }
  if (item.status === "매각") return '<span class="dday past">매각 완료</span>';
  if (item.status === "취하") return '<span class="dday past">취하</span>';
  if (item.is_reauction) return '<span class="dday past">다음 일정 확인 필요</span>';
  return '<span class="dday past">지난 회차</span>';
}
function areaHtml(item) {
  if (item.building_pyeong == null) return "확인 필요";
  const m2 = item.building_m2 ? ` <small>(${Number(item.building_m2).toFixed(2)}㎡)</small>` : "";
  return `${Number(item.building_pyeong).toFixed(2)}평${m2}`;
}
function appraisalGap(item) {
  if (item.discount_vs_appraisal == null) return "확인 필요";
  const value = Number(item.discount_vs_appraisal);
  return value >= 0 ? `${value.toFixed(1)}% 할인` : `${Math.abs(value).toFixed(1)}% 할증`;
}
function match(item) {
  if (state.district && item.district !== state.district) return false;
  if (state.status && item.status !== state.status) return false;
  if (state.source && item.source_type !== state.source) return false;
  if (state.interest && !item.is_interest) return false;
  if (state.upcoming && !item.is_upcoming) return false;
  if (state.failedOnly && !item.is_reauction) return false;
  if (state.q) {
    const hay = [item.complex, item.address, item.case_no, item.district, item.status, statusLabel(item), item.auction_kind, item.next_bid_date, item.last_bid_date, ...(item.risk_tags || [])].join(" ").toLowerCase();
    if (!state.q.split(/\s+/).filter(Boolean).every((word) => hay.includes(word))) return false;
  }
  return true;
}
function cardHtml(item) {
  if (item.source_type === "onbid" && !(item.risk_tags || []).includes(sourceLabel(item))) {
    item.risk_tags = [sourceLabel(item), ...(item.risk_tags || [])];
  }
  const tags = (item.risk_tags || []).map((tag) => `<span class="tag">${esc(tag)}</span>`).join("");
  const interest = item.is_interest ? '<span class="interest-label">관심 면적</span>' : "";
  const ratio = item.minimum_ratio != null ? `<em>${esc(item.minimum_ratio)}%</em>` : "";
  const final = item.final_price != null ? `<div class="metric"><span class="metric-label">매각가</span><strong class="metric-value">${money(item.final_price)}</strong></div>` : `<div class="metric"><span class="metric-label">감정가 대비</span><strong class="metric-value">${appraisalGap(item)}</strong></div>`;
  const nextDate = item.next_bid_date || item.bid_date;
  const dateTitle = item.next_bid_date ? "다음 입찰일" : "최근 입찰일";
  const lastDate = item.last_bid_date ? `<span>직전 회차 ${dateLabel(item.last_bid_date)}</span>` : "";
  return `<li class="auction-card${item.is_interest ? " interest" : ""}${item.is_upcoming ? " upcoming" : ""}">
    <div class="card-head">
      <div>
        <div class="card-kicker"><span class="status-badge ${statusClass(statusLabel(item))}">${esc(statusLabel(item))}</span><span>${esc(item.district || "울산")}</span>${item.auction_round ? `<span>${esc(item.auction_round)}회차</span>` : ""}${interest}</div>
        <h3 class="card-title"><a href="${esc(item.source_url)}" target="_blank" rel="noopener">${esc(item.complex)}</a></h3>
        <p class="card-address">${esc(item.address)}</p>
      </div>
      <div class="bid-date"><span>${dateTitle}</span><strong>${dateLabel(nextDate)}</strong>${ddayHtml(item)}</div>
    </div>
    <div class="metrics">
      <div class="metric"><span class="metric-label">공개목록 건물면적</span><strong class="metric-value">${areaHtml(item)}</strong></div>
      <div class="metric"><span class="metric-label">감정가</span><strong class="metric-value">${money(item.appraisal)}</strong></div>
      <div class="metric"><span class="metric-label">최저가</span><strong class="metric-value">${money(item.minimum_price)}${ratio}</strong></div>
      ${final}
    </div>
    <div class="card-foot"><span class="case">사건 ${esc(item.case_display || item.case_no)}</span>${tags}${lastDate}<span>${esc(item.area_note || "면적 상세 확인 필요")}</span><span class="card-actions"><button class="text-btn" data-detail-id="${esc(item.id)}">상세 보기</button><a class="text-btn" href="${esc(item.official_url)}" target="_blank" rel="noopener">${item.source_type === "onbid" ? "온비드 원문" : "법원 원문"}</a></span></div>
  </li>`;
}
function sortRows(rows) {
  return rows.slice().sort((a, b) => {
    if (state.sort === "minimum") return (a.minimum_ratio ?? 999) - (b.minimum_ratio ?? 999);
    if (state.sort === "discount") return (b.discount_vs_appraisal ?? -1) - (a.discount_vs_appraisal ?? -1);
    if (state.sort === "next_bid_date") {
      const ad = a.next_bid_date || "9999-99-99";
      const bd = b.next_bid_date || "9999-99-99";
      return `${ad}${a.case_no || ""}`.localeCompare(`${bd}${b.case_no || ""}`);
    }
    return `${b.bid_date || ""}${b.case_no || ""}`.localeCompare(`${a.bid_date || ""}${a.case_no || ""}`);
  });
}
function render() {
  const rows = sortRows(auctions.filter(match));
  const countHtml = `<b>${rows.length}</b>건`;
  $("#resultCount").innerHTML = countHtml;
  $("#resultCountMirror").innerHTML = countHtml;
  $("#resultCountLabel").innerHTML = countHtml;
  const shown = rows.slice(0, state.limit);
  listEl.innerHTML = shown.length ? shown.map(cardHtml).join("") : '<li class="empty"><strong>조건에 맞는 경매 물건이 없습니다.</strong>지역·면적 필터를 줄이거나 “유찰 후 재매각만”·“입찰 예정만”을 해제해 보세요.</li>';
  $("#more").innerHTML = rows.length > state.limit ? `<button type="button" id="moreBtn">${rows.length - state.limit}건 더 보기</button>` : "";
  document.querySelectorAll("#auctionList .auction-card").forEach((card, index) => {
    const badge = document.createElement("span");
    badge.className = "source-badge " + sourceClass(shown[index]);
    badge.textContent = sourceLabel(shown[index]);
    card.querySelector(".card-kicker")?.prepend(badge);
  });
  document.querySelectorAll("[data-detail-id]").forEach((button) => button.addEventListener("click", () => openDetail(button.dataset.detailId)));
  const more = $("#moreBtn");
  if (more) more.addEventListener("click", () => { state.limit += 30; render(); });
}
function detailHtml(item) {
  const tags = (item.risk_tags || []).length ? item.risk_tags.join(", ") : "표시된 특이사항 없음";
  const nextDate = item.next_bid_date || "";
  const history = (item.auction_history || []).map((event) => `${dateLabel(event.bid_date)} ${event.status || ""}${event.auction_round ? ` · ${event.auction_round}회` : ""}`).join(" → ");
  const tracking = item.is_reauction ? `유찰 ${item.failed_count || 0}회 후 ${item.is_upcoming ? "재매각 예정" : "재매각 일정 확인 필요"}` : "신건 또는 유찰 이력 없음";
  return `<div class="dialog-inner"><div class="dialog-head"><div><div class="card-kicker"><span class="status-badge ${statusClass(statusLabel(item))}">${esc(statusLabel(item))}</span><span>${esc(item.district)} · ${esc(item.case_display || item.case_no)}</span></div><h2>${esc(item.complex)}</h2><p>${esc(item.address)}</p></div><button class="close-dialog" type="button" aria-label="닫기">×</button></div><div class="detail-grid"><div class="detail-item"><span>${nextDate ? "다음 입찰일" : "최근 입찰일"}</span><strong>${dateLabel(nextDate || item.bid_date)} · ${item.is_upcoming ? "입찰 예정" : "지난 회차"}</strong></div>${item.last_bid_date ? `<div class="detail-item"><span>직전 입찰일</span><strong>${dateLabel(item.last_bid_date)}</strong></div>` : ""}<div class="detail-item"><span>유찰·재매각 추적</span><strong>${esc(tracking)}</strong></div><div class="detail-item"><span>공개목록 건물면적</span><strong>${areaHtml(item)}</strong></div><div class="detail-item"><span>감정가</span><strong>${fullWon(item.appraisal)}</strong></div><div class="detail-item"><span>최저가</span><strong>${fullWon(item.minimum_price)}${item.minimum_ratio != null ? ` (${item.minimum_ratio}%)` : ""}</strong></div>${item.final_price != null ? `<div class="detail-item"><span>매각가</span><strong>${fullWon(item.final_price)}</strong></div>` : ""}<div class="detail-item"><span>회차</span><strong>${item.auction_round ? `${item.auction_round}회` : "확인 필요"}</strong></div></div><div class="detail-section"><h3>회차 이력</h3><p>${esc(history || "공개된 회차 이력 없음")}</p></div><div class="detail-section"><h3>초등학교 접근성</h3><p>${esc(item.school_access)}</p></div><div class="detail-section"><h3>권리·임차인 메모</h3><p>${esc(item.rights_note)}</p></div><div class="detail-section"><h3>공개목록 특이사항</h3><p>${esc(tags)}</p></div><div class="detail-section"><h3>최근 실거래가 대비</h3><p>${esc(item.market_note || "실거래가 확인 필요")}</p></div><div class="detail-section"><h3>면적 주의</h3><p>${esc(item.area_note)}</p></div><div class="dialog-actions"><a href="${esc(item.source_url)}" target="_blank" rel="noopener">공개 검색목록 열기</a><a class="secondary" href="${esc(item.official_url)}" target="_blank" rel="noopener">대한민국 법원경매정보</a></div></div>`;
}
function openDetail(id) {
  const item = auctions.find((row) => row.id === id);
  if (!item) return;
  const dialog = $("#detailDialog");
  $("#detailContent").innerHTML = detailHtml(item);
  const actionLinks = dialog.querySelectorAll(".dialog-actions a");
  if (actionLinks[0] && item.source_type === "onbid") actionLinks[0].textContent = "\uc628\ube44\ub4dc \uc6d0\ubb38 \uc5f4\uae30";
  if (actionLinks[1]) actionLinks[1].textContent = originalLabel(item);
  dialog.querySelector(".close-dialog").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); }, { once: true });
  if (typeof dialog.showModal === "function") dialog.showModal();
}
function setPressed(selector, value) { document.querySelectorAll(selector).forEach((el) => el.setAttribute("aria-pressed", String(el.dataset.value === value))); }
document.querySelectorAll("[data-district]").forEach((button) => button.addEventListener("click", () => { state.district = state.district === button.dataset.district ? "" : button.dataset.district; setPressed("[data-district]", state.district); state.limit = 30; render(); }));
document.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => { state.status = state.status === button.dataset.status ? "" : button.dataset.status; setPressed("[data-status]", state.status); state.limit = 30; render(); }));
document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { state.source = state.source === button.dataset.source ? "" : button.dataset.source; setPressed("[data-source]", state.source); state.limit = 30; render(); }));
$("#q").addEventListener("input", (event) => { state.q = event.target.value.trim().toLowerCase(); state.limit = 30; render(); });
$("#interestOnly").addEventListener("click", (event) => { state.interest = !state.interest; event.currentTarget.setAttribute("aria-pressed", String(state.interest)); state.limit = 30; render(); });
$("#upcomingOnly").addEventListener("click", (event) => { state.upcoming = !state.upcoming; event.currentTarget.setAttribute("aria-pressed", String(state.upcoming)); state.limit = 30; render(); });
$("#failedOnly").addEventListener("click", (event) => { state.failedOnly = !state.failedOnly; event.currentTarget.setAttribute("aria-pressed", String(state.failedOnly)); state.limit = 30; render(); });
$("#sort").addEventListener("change", (event) => { state.sort = event.target.value; render(); });
$("#reset").addEventListener("click", () => { state.q = ""; state.district = ""; state.status = ""; state.source = ""; state.interest = false; state.upcoming = false; state.failedOnly = false; state.sort = "next_bid_date"; state.limit = 30; $("#q").value = ""; $("#sort").value = "next_bid_date"; document.querySelectorAll("[data-district], [data-status], [data-source]").forEach((el) => el.setAttribute("aria-pressed", "false")); $("#interestOnly").setAttribute("aria-pressed", "false"); $("#upcomingOnly").setAttribute("aria-pressed", "false"); $("#failedOnly").setAttribute("aria-pressed", "false"); render(); });
$("#detailDialog").addEventListener("cancel", (event) => event.stopPropagation());
render();
"""


def money(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 100_000_000:
        eok = value // 100_000_000
        man = (value % 100_000_000) // 10_000
        return f"{eok}억 {man:,}만" if man else f"{eok}억"
    return f"{round(value / 10_000):,}만"


def build() -> None:
    with DATA.open(encoding="utf-8") as handle:
        data = json.load(handle)
    auctions = data.get("auctions", [])
    source_type_counts = Counter(item.get("source_type", "court") for item in auctions)
    source_order = [("court", "\ubc95\uc6d0\uacbd\ub9e4"), ("onbid", "\uc628\ube44\ub4dc \uacf5\ub9e4")]
    source_counts = Counter(item.get("source_name", "공개 목록") for item in auctions)
    district_counts = Counter(item.get("district", "기타") for item in auctions)
    status_counts = Counter(item.get("status", "확인 필요") for item in auctions)
    upcoming = sum(1 for item in auctions if item.get("is_upcoming"))
    reauction = sum(1 for item in auctions if item.get("is_reauction"))
    interest = sum(1 for item in auctions if item.get("is_interest"))
    discounts = [
        item["discount_vs_appraisal"]
        for item in auctions
        if item.get("is_interest") and item.get("discount_vs_appraisal") is not None
    ]
    max_discount = max(discounts) if discounts else None
    generated = data.get("generated_at", "확인 필요")
    as_of = data.get("as_of", "")
    history_days = data.get("history_days", 90)
    filters = data.get("filters", {})
    sources = data.get("sources", {})
    onbid = sources.get("onbid", {})
    official = sources.get("official", {})
    official_search = sources.get("official_search", {})
    public_list = sources.get("public_list", {})
    market = sources.get("market", {})

    district_order = ["중구", "남구", "북구"]
    district_chips = "".join(
        f'<button class="pill" type="button" data-district="{district}" data-value="{district}" aria-pressed="false">{district}<span class="count">{district_counts.get(district, 0)}</span></button>'
        for district in district_order
    )
    source_chips = "".join(
        f'<button class="pill" type="button" data-source="{source_type}" data-value="{source_type}" aria-pressed="false">{label}<span class="count">{source_type_counts.get(source_type, 0)}</span></button>'
        for source_type, label in source_order
        if source_type_counts.get(source_type)
    )
    status_order = ["\uc785\ucc30 \uc608\uc815", "\uc785\ucc30\uc911", "\uc785\ucc30 \ub9c8\uac10", "\uc720\ucc30", "\ubcc0\uacbd", "\ub9e4\uac01", "\uc9c4\ud589", "\uc2e0\uac74", "\ucde8\ud558"]
    status_chips = "".join(
        f'<button class="pill" type="button" data-status="{status}" data-value="{status}" aria-pressed="false">{status}<span class="count">{status_counts.get(status, 0)}</span></button>'
        for status in status_order if status_counts.get(status)
    )
    payload = json.dumps({"auctions": auctions}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    official_url = official.get("url", "https://www.courtauction.go.kr/")
    official_search_url = official_search.get("url", "https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on")
    onbid_url = onbid.get("url", "https://www.onbid.co.kr/")
    public_url = public_list.get("url", "https://www.winnerauction.co.kr/search/search_list.php?acourt=411&acharge=10&usage_codes=101")
    market_url = market.get("url", "https://rt.molit.go.kr/pt/gis/gis.do?mobileAt=&srhThingSecd=C")
    official_window = filters.get("official_future_window_days", 14)
    notice = (
        f"공식 법원목록에서 다음 {official_window}일의 입찰 예정 {upcoming}건을 확인했습니다. 이 중 유찰 후 재매각 추적 대상은 {reauction}건이며, 최근 {history_days}일 일정목록도 함께 보여줍니다."
        if upcoming
        else f"현재 공식 법원목록의 다음 {official_window}일 예정목록에서 지역 조건에 맞는 물건은 확인되지 않았습니다. 최근 {history_days}일 일정목록의 사례를 함께 표시합니다."
    )
    scope_text = "·".join(filters.get("included_districts", ["중구", "남구", "북구"]))
    excluded_text = "·".join(filters.get("excluded_districts", ["동구", "울주군"]))
    building_range = filters.get("building_pyeong_focus", [24, 40])
    supply_focus = filters.get("supply_pyeong_focus", 32)
    school_minutes = filters.get("school_walk_minutes", 10)
    complex_units = filters.get("large_complex_units", 500)

    body = f'''<div class="shell">
  <header class="topbar">
    <a class="brand" href="#top"><span class="brand-mark">落</span><span><span class="brand-name">울산 아파트 경매</span><span class="brand-sub">공개목록 큐레이션</span></span></a>
    <a class="top-link" href="{official_url}" target="_blank" rel="noopener">대한민국 법원경매정보 ↗</a>
    <a class="top-link" href="{onbid_url}" target="_blank" rel="noopener">\uc628\ube44\ub4dc \uacf5\uc2dd \uac80\uc0c9 \u2197</a>
  </header>

  <main id="top">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">ULSAN APARTMENT AUCTION WATCH</p>
        <h1>울산에서 찾는<br>{building_range[0]}~{building_range[1]}평 아파트 경매</h1>
        <p class="hero-lede">흩어진 경매·공매 공개목록을 한 곳에 모아 <strong>입찰일·최저가·가격 메리트</strong>를 먼저 살펴봅니다. 제목을 누르면 공개 출처로 이동하고, 최종 입찰 전에는 반드시 법원·온비드 원문을 확인하세요.</p>
        <div class="hero-meta"><span class="meta-pill">범위 <b>{scope_text}</b></span><span class="meta-pill">제외 <b>{excluded_text}</b></span><span class="meta-pill">기준일 <b>{as_of or "—"}</b></span></div>
      </div>
      <aside class="criteria-card">
        <p class="criteria-label">MY WATCH CRITERIA</p>
        <h2>이번 감시 조건</h2>
        <ul class="criteria-list"><li>{scope_text} 중심, {excluded_text} 제외</li><li>공급 {supply_focus}평 이상을 우선 검토</li><li>공개목록 건물 {building_range[0]}~{building_range[1]}평 근접</li><li>초등학교 실제 도보 {school_minutes}분 이내 우선</li><li>{complex_units}세대 이상 대단지 우선</li></ul>
        <p class="criteria-foot">학교·세대수·권리·임차인 정보는 자동 확정하지 않습니다. 원문 상세와 현장 확인이 필요한 항목입니다.</p>
      </aside>
    </section>

    <section class="stats" aria-label="요약 통계">
      <div class="stat"><span class="stat-label">범위 내 아파트</span><strong class="stat-value">{len(auctions)}</strong><span class="stat-note">공개목록에서 확인된 건</span></div>
      <div class="stat"><span class="stat-label">{building_range[0]}~{building_range[1]}평 관심</span><strong class="stat-value accent">{interest}</strong><span class="stat-note">건물면적 기준</span></div>
      <div class="stat"><span class="stat-label">입찰 예정</span><strong class="stat-value green">{upcoming}</strong><span class="stat-note">오늘 이후·매각/취하 제외</span></div>
      <div class="stat"><span class="stat-label">유찰 후 재매각</span><strong class="stat-value accent">{reauction}</strong><span class="stat-note">유찰 횟수 확인 건</span></div>
      <div class="stat"><span class="stat-label">관심 면적 최대 할인</span><strong class="stat-value accent">{f"{max_discount:.1f}%" if max_discount is not None else "—"}</strong><span class="stat-note">감정가 대비, 참고용</span></div>
    </section>

    <div class="notice"><span class="notice-icon">!</span><p>{notice}<br><b>중요:</b> 법원·온비드 공개목록의 ‘건물면적’은 전용면적과 다를 수 있어 관심 면적 충족 여부를 최종 확정하지 않습니다. 입찰 전 공식 원문과 공고문을 확인하세요.</p></div>

    <section class="filters-wrap" aria-label="경매 검색 및 필터">
      <div class="filters">
        <div class="filter-row"><span class="filter-label">\ucd9c\ucc98</span>{source_chips}</div>
        <div class="search-row"><div class="search-box"><input type="search" id="q" placeholder="단지명, 주소, 사건번호, 특이사항 검색" aria-label="경매 검색"></div><select id="sort" aria-label="정렬"><option value="next_bid_date">다음 입찰일 빠른순</option><option value="bid_date">입찰일 최신순</option><option value="minimum">최저가율 낮은순</option><option value="discount">감정가 할인 큰순</option></select></div>
        <div class="filter-row"><span class="filter-label">지역</span>{district_chips}<span class="filter-divider"></span><span class="filter-label">상태</span>{status_chips}<button class="reset-btn" id="reset" type="button">필터 초기화</button></div>
        <div class="filter-row"><button class="pill" id="interestOnly" type="button" aria-pressed="false">{building_range[0]}~{building_range[1]}평만</button><button class="pill" id="upcomingOnly" type="button" aria-pressed="false">입찰 예정만</button><button class="pill" id="failedOnly" type="button" aria-pressed="false">유찰 후 재매각만<span class="count">{reauction}</span></button><span class="result-count" id="resultCount"></span></div>
      </div>
    </section>

    <div class="results-bar"><h2>울산 아파트 경매 목록</h2><span class="result-count" id="resultCountMirror"></span><span class="sorter"><span class="result-count">총 <span id="resultCountLabel"></span></span></span></div>
    <ul class="auction-list" id="auctionList"></ul>
    <div class="more" id="more"></div>

    <section class="lower-grid">
      <div class="info-panel"><h2>선별 기준</h2><p>공개목록에서 자동으로 표시하는 범위입니다.</p><ul class="info-list"><li><span>포함 지역</span><b>{scope_text}</b></li><li><span>제외 지역</span><b>{excluded_text}</b></li><li><span>면적 기준</span><b>건물 {building_range[0]}~{building_range[1]}평 근접</b></li><li><span>공급면적</span><b>{supply_focus}평 이상 우선 · 원문 확인</b></li><li><span>학교·대단지</span><b>도보 {school_minutes}분 · {complex_units}세대 우선</b></li></ul></div>
      <div class="info-panel"><h2>데이터 출처</h2><p>목록은 참고용 큐레이션입니다. 권리분석이나 입찰 판단의 근거로 단독 사용하지 마세요.</p><ul class="info-list"><li><span>법원 원문</span><b><a class="source-link" href="{official_url}" target="_blank" rel="noopener">{official.get("name", "대한민국 법원경매정보")} ↗</a></b></li><li><span>법원 공식 검색</span><b><a class="source-link" href="{official_search_url}" target="_blank" rel="noopener">다음 매각기일·유찰횟수 ↗</a></b></li><li><span>온비드 공매</span><b><a class="source-link" href="{onbid_url}" target="_blank" rel="noopener">{onbid.get("name", "온비드 공식 검색목록")} ↗</a></b></li><li><span>공개 목록</span><b><a class="source-link" href="{public_url}" target="_blank" rel="noopener">{public_list.get("name", "공개 검색목록")} ↗</a></b></li><li><span>실거래가</span><b><a class="source-link" href="{market_url}" target="_blank" rel="noopener">{market.get("name", "국토교통부 실거래가")} ↗</a></b></li><li><span>최근 갱신</span><b>{generated}</b></li><li><span>확인 범위</span><b>공식 다음 {official_window}일 + 최근 {history_days}일</b></li></ul></div>
    </section>

    <p class="footer">데이터 갱신: <code>python collect.py</code> 실행 후 <code>python build_site.py</code>를 실행하세요. 유찰·재매각 일정은 공개목록에서 확인되는 범위만 추적하며, 법원·온비드 공개목록의 주소·면적·가격·상태와 공식 원문이 다를 수 있습니다. 입찰 전 사건 상세, 공고문, 감정평가서, 현황조사서, 등기사항증명서 및 현장을 직접 확인하세요. <a href="{official_url}" target="_blank" rel="noopener">법원 원문 확인 ↗</a> · <a href="{onbid_url}" target="_blank" rel="noopener">온비드 원문 확인 ↗</a></p>
  </main>
</div>
<dialog id="detailDialog"><div id="detailContent"></div></dialog>
<script>window.__AUCTIONS__ = {payload};</script>
<script>{JS}</script>'''

    title = "울산 아파트 경매 모아보기"
    artifact = f"<title>{title}</title>\n<style>{CSS}</style>\n{body}"
    full = f'''<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#274750"><title>{title}</title><style>{CSS}</style></head>
<body>{body}</body>
</html>'''

    for output_dir in (SITE, DOCS):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "artifact.html").write_text(artifact, encoding="utf-8")
        (output_dir / "index.html").write_text(full, encoding="utf-8")

    print(f"생성 완료 ({len(auctions)}건)")
    print(f"  {SITE / 'index.html'}")
    print(f"  {DOCS / 'index.html'} (GitHub Pages)")


if __name__ == "__main__":
    build()
