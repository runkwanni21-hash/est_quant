"""대시보드 FastAPI 앱 — 텔레그램 없이 브라우저에서 바로 투자 분석."""

from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from typing import Any

# FastAPI 타입을 모듈 레벨에서 import — from __future__ import annotations 사용 시
# create_app() 클로저 내부 import는 FastAPI가 타입 힌트를 전역 스코프에서 resolve할 때
# 찾지 못하므로, 모듈 레벨 import가 필수.
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    # 타입 체크용 플레이스홀더
    Request = object  # type: ignore[assignment, misc]

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 세션 저장소 (메모리, 서버 재시작 시 초기화)
# ─────────────────────────────────────────────────────────────────────────────
_sessions: dict[str, float] = {}   # token → expiry (unix timestamp)
_SESSION_TTL = 86400.0             # 일반 사용자: 24시간
_MASTER_TTL  = 86400.0 * 3650     # 마스터: 10년 (사실상 서버 재시작 전까지 무제한)
_SESSION_MAX = 50                  # 최대 동시 세션 수

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tele Quant — 로그인</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,'Malgun Gothic',sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:40px 36px;
  width:340px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.logo{font-size:36px;margin-bottom:12px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
.sub{font-size:12px;color:#8b949e;margin-bottom:28px}
input{width:100%;background:#21262d;border:1px solid #30363d;border-radius:8px;
  color:#e6edf3;padding:11px 14px;font-size:14px;font-family:inherit;outline:none;
  letter-spacing:2px;margin-bottom:14px}
input:focus{border-color:#58a6ff}
button{width:100%;background:#238636;border:none;border-radius:8px;color:#fff;
  font-size:14px;font-weight:700;padding:12px;cursor:pointer;font-family:inherit;
  transition:opacity .15s}
button:hover{opacity:.88}
.err{color:#f85149;font-size:12px;margin-top:10px;min-height:18px}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #3d444d;
  border-top-color:#58a6ff;border-radius:50%;animation:spin .6s linear infinite;
  vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.lock{font-size:13px;color:#8b949e;margin-top:20px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🔐</div>
  <h1>Tele Quant Dashboard</h1>
  <div class="sub">접근 제한 구역 — 비밀번호를 입력하세요</div>
  <input type="password" id="pw" placeholder="비밀번호" autofocus
    onkeydown="if(event.key==='Enter')doLogin()">
  <button onclick="doLogin()">로그인</button>
  <div class="err" id="err"></div>
  <div class="lock">🔒 허가된 사용자만 접근 가능</div>
</div>
<script>
async function doLogin() {
  const pw = document.getElementById('pw').value;
  if(!pw) return;
  const btn = document.querySelector('button');
  const err = document.getElementById('err');
  btn.innerHTML = '<span class="spinner"></span>확인 중...';
  btn.disabled = true;
  err.textContent = '';
  try {
    const r = await fetch('/login', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({password: pw})
    });
    const d = await r.json();
    if(d.ok) {
      window.location.href = '/';
    } else {
      err.textContent = '비밀번호가 틀렸습니다.';
      document.getElementById('pw').value = '';
      document.getElementById('pw').focus();
    }
  } catch(e) {
    err.textContent = '연결 오류: ' + e.message;
  } finally {
    btn.innerHTML = '로그인';
    btn.disabled = false;
  }
}
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tele Quant Dashboard</title>
<style>
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--bg4:#2d333b;
  --border:#30363d;--border2:#3d444d;
  --text:#e6edf3;--muted:#8b949e;--muted2:#6e7681;
  --green:#3fb950;--red:#f85149;--yellow:#e3b341;--blue:#58a6ff;--purple:#bc8cff;--orange:#f0883e;
  --sidebar:220px;--radius:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;font-size:14px;display:flex;height:100vh;overflow:hidden}

/* ── 사이드바 ─────────────────────────────────────────────── */
.sidebar{width:var(--sidebar);min-width:var(--sidebar);background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.logo{padding:16px 14px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)}
.logo-icon{font-size:20px}
.logo-text{font-size:15px;font-weight:700;color:var(--text)}
.logo-badge{font-size:10px;background:var(--blue);color:#fff;padding:1px 6px;border-radius:10px;margin-left:auto}
nav{flex:1;padding:8px 0;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 14px;cursor:pointer;color:var(--muted);font-size:13px;border-left:3px solid transparent;transition:all .15s;user-select:none}
.nav-item:hover{color:var(--text);background:var(--bg3)}
.nav-item.active{color:var(--blue);background:rgba(88,166,255,.08);border-left-color:var(--blue)}
.nav-item .icon{font-size:15px;width:18px;text-align:center}
.nav-section{padding:12px 14px 4px;font-size:10px;color:var(--muted2);text-transform:uppercase;letter-spacing:.08em}
.sidebar-footer{padding:10px 14px;border-top:1px solid var(--border)}
.status-pill{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:6px;font-size:11px;color:var(--muted);background:var(--bg3);margin-bottom:4px;cursor:pointer}
.status-pill:hover{background:var(--bg4)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--muted2)}
.dot.on{background:var(--green)}
.dot.off{background:var(--red)}
.dot.warn{background:var(--yellow)}

/* ── 메인 ─────────────────────────────────────────────────── */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;gap:10px;min-height:46px}
.topbar-title{font-size:15px;font-weight:700;color:var(--text)}
.topbar-sub{font-size:12px;color:var(--muted)}
.spacer{flex:1}
.mkt-btn{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--muted);transition:all .15s}
.mkt-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.mkt-btn:hover:not(.active){border-color:var(--blue);color:var(--blue)}
.btn{padding:6px 14px;border-radius:var(--radius);cursor:pointer;border:1px solid var(--border);background:var(--bg3);color:var(--text);font-size:13px;transition:all .15s;font-family:inherit}
.btn:hover{background:var(--bg4)}
.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
.btn.primary:hover{opacity:.88}
.btn.success{background:var(--green);border-color:var(--green);color:#fff}
.btn.danger{background:var(--red);border-color:var(--red);color:#fff}
.btn.sm{padding:4px 10px;font-size:12px}
.content{flex:1;overflow-y:auto;padding:16px 20px}

/* ── 페이지 ─────────────────────────────────────────────── */
.page{display:none}.page.active{display:block}

/* ── 그리드 / 카드 ──────────────────────────────────────── */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;overflow:hidden}
.card-title{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;font-weight:600}
.kpi{display:flex;flex-direction:column}
.kpi-val{font-size:22px;font-weight:700;line-height:1.2}
.kpi-sub{font-size:12px;color:var(--muted);margin-top:3px}
.kpi-chg{font-size:13px;font-weight:600;margin-top:2px}

/* ── 색상 유틸 ──────────────────────────────────────────── */
.up{color:var(--green)} .dn{color:var(--red)} .neu{color:var(--muted)}
.tag-green{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.25)}
.tag-red{background:rgba(248,81,73,.15);color:var(--red);border:1px solid rgba(248,81,73,.25)}
.tag-yellow{background:rgba(227,179,65,.15);color:var(--yellow);border:1px solid rgba(227,179,65,.25)}
.tag-blue{background:rgba(88,166,255,.12);color:var(--blue);border:1px solid rgba(88,166,255,.22)}
.tag-purple{background:rgba(188,140,255,.12);color:var(--purple);border:1px solid rgba(188,140,255,.22)}

/* ── 매크로 패널 ─────────────────────────────────────────── */
.macro-row{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg3);margin-bottom:6px}
.macro-row:last-child{margin-bottom:0}
.macro-label{font-size:12px;color:var(--muted);min-width:80px}
.macro-val{font-size:15px;font-weight:700}
.macro-chg{font-size:12px;min-width:60px;text-align:right}
.regime-bar{margin-top:10px;padding:10px 14px;border-radius:6px;text-align:center;font-size:13px;font-weight:700}

/* ── 스크리너 테이블 ─────────────────────────────────────── */
.tbl-wrap{overflow-x:auto;overflow-y:auto;max-height:460px;border-radius:var(--radius);border:1px solid var(--border)}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{padding:8px 12px;text-align:left;font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg3);z-index:1;white-space:nowrap}
.tbl td{padding:8px 12px;border-bottom:1px solid rgba(48,54,61,.6);vertical-align:middle}
.tbl tr:hover td{background:rgba(88,166,255,.04);cursor:pointer}
.tbl tr:last-child td{border-bottom:none}
.sym{font-weight:700;color:var(--blue);font-size:13px}
.name-cell{color:var(--muted);max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.score-wrap{display:inline-flex;align-items:center;gap:7px}
.score-num{font-weight:700;min-width:26px;text-align:right;font-size:13px}
.score-track{width:46px;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden}
.score-fill{height:100%;border-radius:3px}
.sig{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap}

/* ── 종목 상세 ──────────────────────────────────────────── */
.search-bar{display:flex;gap:8px;margin-bottom:14px}
.inp{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);padding:8px 12px;font-size:14px;font-family:inherit;flex:1}
.inp:focus{outline:none;border-color:var(--blue)}
.sel{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);padding:8px 10px;font-size:13px;font-family:inherit}
.detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.detail-kpi{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:11px 13px}
.detail-kpi .label{font-size:11px;color:var(--muted);margin-bottom:3px}
.detail-kpi .value{font-size:18px;font-weight:700}
.detail-kpi .sub{font-size:11px;color:var(--muted);margin-top:2px}
.report-box{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:14px;font-size:12px;line-height:1.8;white-space:pre-wrap;word-break:break-word;font-family:'Consolas','Malgun Gothic',monospace;max-height:500px;overflow-y:auto}

/* ── 브리핑 ─────────────────────────────────────────────── */
.briefing-header{display:flex;gap:8px;margin-bottom:14px;align-items:center}
.briefing-box{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:18px;font-size:13px;line-height:1.9;white-space:pre-wrap;word-break:break-word;max-height:calc(100vh - 200px);overflow-y:auto}

/* ── 텔레그램 설정 ──────────────────────────────────────── */
.form-section{margin-bottom:20px}
.form-section-title{font-size:13px;font-weight:700;color:var(--text);margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.form-row{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.form-row label{font-size:12px;color:var(--muted);font-weight:600}
.form-row .hint{font-size:11px;color:var(--muted2);margin-top:3px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.toggle-row{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;margin-bottom:8px}
.toggle-info{flex:1}
.toggle-info .t-title{font-size:13px;font-weight:600}
.toggle-info .t-desc{font-size:11px;color:var(--muted);margin-top:2px}
.toggle{position:relative;width:40px;height:22px;flex-shrink:0;margin-left:12px}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;inset:0;background:var(--bg4);border-radius:22px;transition:.2s;border:1px solid var(--border2)}
.slider:before{position:absolute;content:"";height:16px;width:16px;left:2px;bottom:2px;background:var(--muted);border-radius:50%;transition:.2s}
input:checked+.slider{background:var(--blue);border-color:var(--blue)}
input:checked+.slider:before{transform:translateX(18px);background:#fff}
.info-box{background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.2);border-radius:6px;padding:10px 13px;font-size:12px;color:var(--muted);line-height:1.7;margin-bottom:14px}
.info-box.warn{background:rgba(227,179,65,.08);border-color:rgba(227,179,65,.2)}
.info-box.success{background:rgba(63,185,80,.08);border-color:rgba(63,185,80,.2)}
.ollama-status{display:flex;align-items:center;gap:10px;padding:12px 14px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;margin-bottom:12px}
.ollama-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}

/* ── 스케줄러 ────────────────────────────────────────────── */
.sched-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:12px}
.sched-status{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.sched-actions{display:flex;gap:8px;flex-wrap:wrap}

/* ── 로딩 / 상태 ─────────────────────────────────────────── */
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--border2);border-top-color:var(--blue);border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.loading{padding:30px;text-align:center;color:var(--muted)}
.empty{padding:20px;text-align:center;color:var(--muted2);font-size:13px}
.err-msg{color:var(--red);font-size:12px;padding:6px 0}

/* ── 토스트 ─────────────────────────────────────────────── */
.toast{position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:var(--radius);font-size:13px;font-weight:600;opacity:0;transition:opacity .25s;pointer-events:none;z-index:999;max-width:320px}
.toast.show{opacity:1}
.toast.ok{background:rgba(63,185,80,.95);color:#fff}
.toast.err{background:rgba(248,81,73,.95);color:#fff}
.toast.info{background:rgba(88,166,255,.95);color:#fff}

/* ── 반응형 ─────────────────────────────────────────────── */
@media(max-width:900px){
  .sidebar{display:none}
  .grid-3,.grid-4{grid-template-columns:1fr 1fr}
  .detail-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:600px){
  .grid-2,.grid-3,.grid-4{grid-template-columns:1fr}
  .detail-grid{grid-template-columns:1fr}
}
</style>
</head>
<body>

<!-- ── 사이드바 ──────────────────────────────────────────────── -->
<aside class="sidebar">
  <div class="logo">
    <span class="logo-icon">📊</span>
    <span class="logo-text">Tele Quant</span>
    <span class="logo-badge">Beta</span>
  </div>
  <nav>
    <div class="nav-section">분석</div>
    <div class="nav-item active" onclick="nav('market')" id="nav-market">
      <span class="icon">📈</span>시장 개요
    </div>
    <div class="nav-item" onclick="nav('screener')" id="nav-screener">
      <span class="icon">🔍</span>종목 스크리너
    </div>
    <div class="nav-item" onclick="nav('analysis')" id="nav-analysis">
      <span class="icon">🧮</span>종목 상세 분석
    </div>
    <div class="nav-item" onclick="nav('briefing')" id="nav-briefing">
      <span class="icon">📋</span>4H 브리핑
    </div>
    <div class="nav-section">자동화</div>
    <div class="nav-item" onclick="nav('telegram')" id="nav-telegram">
      <span class="icon">💬</span>텔레그램 설정
    </div>
    <div class="nav-item" onclick="nav('scheduler')" id="nav-scheduler">
      <span class="icon">⏰</span>4H 스케줄러
    </div>
    <div class="nav-section">시스템</div>
    <div class="nav-item" onclick="nav('datasource')" id="nav-datasource">
      <span class="icon">🔌</span>데이터 소스
    </div>
    <div class="nav-item" onclick="nav('ollama')" id="nav-ollama">
      <span class="icon">🤖</span>AI 모델 (Ollama)
    </div>
  </nav>
  <div class="sidebar-footer">
    <div class="status-pill" onclick="nav('ollama')" id="pill-ollama">
      <span class="dot" id="dot-ollama"></span>
      <span id="label-ollama">Ollama 확인 중...</span>
    </div>
    <div class="status-pill" onclick="nav('scheduler')" id="pill-sched">
      <span class="dot" id="dot-sched"></span>
      <span id="label-sched">4H 스케줄러</span>
    </div>
    <div style="font-size:10px;color:var(--muted2);margin-top:6px;text-align:center">
      공개 정보 기반 · 투자 책임은 본인에게 있음
    </div>
    <a href="/logout" style="display:block;margin-top:8px;padding:6px 10px;border-radius:6px;
      font-size:11px;color:var(--muted2);text-decoration:none;text-align:center;
      border:1px solid var(--border);transition:all .15s"
      onmouseover="this.style.color='var(--red)';this.style.borderColor='rgba(248,81,73,.4)'"
      onmouseout="this.style.color='var(--muted2)';this.style.borderColor='var(--border)'">
      🔓 로그아웃
    </a>
  </div>
</aside>

<!-- ── 메인 ─────────────────────────────────────────────────── -->
<div class="main">
  <div class="topbar">
    <span class="topbar-title" id="page-title">시장 개요</span>
    <span class="topbar-sub" id="page-sub"></span>
    <div class="spacer"></div>
    <button class="mkt-btn active" id="btn-kr" onclick="setMkt('KR')">🇰🇷 KR</button>
    <button class="mkt-btn" id="btn-us" onclick="setMkt('US')">🇺🇸 US</button>
    <button class="mkt-btn" id="btn-all" onclick="setMkt('ALL')">🌍 ALL</button>
    <button class="btn sm" onclick="refreshCurrent()" style="margin-left:6px">↺ 새로고침</button>
  </div>

  <div class="content">

    <!-- ── 시장 개요 ───────────────────────────────────────── -->
    <div class="page active" id="page-market">
      <div class="grid-2" style="margin-bottom:12px">
        <div class="card" id="macro-card">
          <div class="card-title">📡 실시간 매크로</div>
          <div id="macro-body"><div class="loading"><span class="spinner"></span>수집 중...</div></div>
        </div>
        <div class="card">
          <div class="card-title">📊 시장 지수 변화</div>
          <div id="index-body"><div class="loading"><span class="spinner"></span>수집 중...</div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">⚡ 오늘의 Top 관찰 종목</div>
        <div id="top-picks"><div class="loading"><span class="spinner"></span>스크리닝 중...</div></div>
      </div>
    </div>

    <!-- ── 종목 스크리너 ──────────────────────────────────── -->
    <div class="page" id="page-screener">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div style="font-size:13px;color:var(--muted)" id="screener-meta">워치리스트 종목 병렬 스크리닝</div>
        <button class="btn sm primary" onclick="loadScreener()">↺ 재스크리닝</button>
      </div>
      <div class="tbl-wrap" id="screener-wrap">
        <div class="loading"><span class="spinner"></span>스크리닝 중 (최대 30초)...</div>
      </div>
    </div>

    <!-- ── 종목 상세 분석 ─────────────────────────────────── -->
    <div class="page" id="page-analysis">
      <div class="search-bar">
        <input class="inp" id="a-ticker" placeholder="종목코드 입력 (예: NVDA, 005930.KS, 삼성전자)" onkeydown="if(event.key==='Enter')doAnalysis()">
        <select class="sel" id="a-mkt"><option value="US">US</option><option value="KR">KR</option></select>
        <button class="btn primary" onclick="doAnalysis()">🔍 분석</button>
      </div>
      <div id="analysis-result"></div>
    </div>

    <!-- ── 4H 브리핑 ──────────────────────────────────────── -->
    <div class="page" id="page-briefing">
      <div class="briefing-header">
        <button class="mkt-btn active" id="br-kr" onclick="loadBriefing('KR')">🇰🇷 KR</button>
        <button class="mkt-btn" id="br-us" onclick="loadBriefing('US')">🇺🇸 US</button>
        <div class="spacer"></div>
        <button class="btn sm primary" onclick="loadBriefing(curBriefMkt)">↺ 재생성</button>
      </div>
      <div class="briefing-box" id="briefing-body">
        <div class="loading"><span class="spinner"></span>브리핑 생성 중...</div>
      </div>
    </div>

    <!-- ── 텔레그램 설정 ──────────────────────────────────── -->
    <div class="page" id="page-telegram">
      <div class="info-box" style="margin-bottom:16px">
        💬 <strong>텔레그램 봇</strong>을 연결하면 4H 브리핑·급등 알림을 자동 수신할 수 있습니다.<br>
        봇이 없어도 대시보드 기능은 정상 동작합니다.
      </div>
      <div class="form-section">
        <div class="form-section-title">발신 봇 (브리핑/알림 전송)</div>
        <div class="form-grid">
          <div class="form-row">
            <label>Bot Token</label>
            <input class="inp" id="cfg-bot-token" placeholder="7xxxxxxxxx:AAF...">
            <div class="hint">@BotFather → /newbot 으로 발급</div>
          </div>
          <div class="form-row">
            <label>Target Chat ID</label>
            <input class="inp" id="cfg-chat-id" placeholder="-1001234567890 또는 내 chat_id">
            <div class="hint">@userinfobot 에서 확인</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn primary" onclick="saveTelegram()">💾 저장</button>
          <button class="btn" onclick="testTelegram()">📨 테스트 메시지 발송</button>
        </div>
        <div id="tg-result" style="margin-top:8px"></div>
      </div>
      <div class="form-section">
        <div class="form-section-title">수집 채널 (텔레그램 리포트 자동 수집)</div>
        <div class="info-box warn">
          채널 수집에는 <strong>텔레그램 사용자 API</strong>(my.telegram.org/apps)가 필요합니다.<br>
          yfinance + 뉴스 API 만으로도 기본 분석은 동작합니다.
        </div>
        <div class="form-grid">
          <div class="form-row">
            <label>API ID</label>
            <input class="inp" id="cfg-api-id" placeholder="12345678">
          </div>
          <div class="form-row">
            <label>API Hash</label>
            <input class="inp" id="cfg-api-hash" placeholder="abc123...">
          </div>
          <div class="form-row">
            <label>전화번호</label>
            <input class="inp" id="cfg-phone" placeholder="+821012345678">
          </div>
        </div>
        <div class="form-row" style="margin-top:8px">
          <label>수집 채널 (쉼표 구분)</label>
          <input class="inp" id="cfg-chats" placeholder="KiwoomResearch,HanaResearch,meritz_research">
          <div class="hint">채널명 확인: uv run tele-quant list-chats</div>
        </div>
        <button class="btn primary" onclick="saveTelegramAdv()" style="margin-top:8px">💾 저장</button>
      </div>
    </div>

    <!-- ── 4H 스케줄러 ────────────────────────────────────── -->
    <div class="page" id="page-scheduler">
      <div class="sched-card">
        <div class="sched-status">
          <div>
            <div style="font-size:15px;font-weight:700" id="sched-status-text">확인 중...</div>
            <div style="font-size:12px;color:var(--muted);margin-top:3px" id="sched-next">—</div>
          </div>
          <label class="toggle">
            <input type="checkbox" id="sched-toggle" onchange="toggleScheduler()">
            <span class="slider"></span>
          </label>
        </div>
        <div class="form-grid" style="margin-bottom:12px">
          <div class="form-row">
            <label>브리핑 시장</label>
            <select class="sel" id="sched-market" style="width:100%">
              <option value="KR">🇰🇷 한국 (KR)</option>
              <option value="US">🇺🇸 미국 (US)</option>
              <option value="ALL">🌍 전체 (KR+US)</option>
            </select>
          </div>
          <div class="form-row">
            <label>실행 주기</label>
            <select class="sel" id="sched-interval" style="width:100%">
              <option value="4">4시간 (기본)</option>
              <option value="6">6시간</option>
              <option value="8">8시간</option>
              <option value="2">2시간 (빠른 업데이트)</option>
            </select>
          </div>
        </div>
        <div class="sched-actions">
          <button class="btn sm success" onclick="schedRunNow()">▶ 지금 즉시 실행</button>
          <button class="btn sm" onclick="loadSchedulerStatus()">↺ 상태 새로고침</button>
        </div>
      </div>
      <div class="info-box">
        ⏰ <strong>스케줄러 동작 방식</strong><br>
        대시보드 서버가 켜진 동안 백그라운드에서 자동 실행됩니다.<br>
        텔레그램 봇 토큰이 설정된 경우 결과를 자동 전송합니다.<br>
        서버를 닫으면 스케줄러도 함께 종료됩니다.
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:8px" id="sched-history"></div>
    </div>

    <!-- ── 데이터 소스 ─────────────────────────────────────── -->
    <div class="page" id="page-datasource">
      <div class="info-box" style="margin-bottom:14px">
        🔌 활성화된 소스만 데이터를 수집합니다. API 키가 없는 소스는 자동으로 비활성화됩니다.
      </div>
      <div id="datasource-list">
        <div class="loading"><span class="spinner"></span>로드 중...</div>
      </div>
      <button class="btn primary" onclick="saveDatasources()" style="margin-top:14px">💾 데이터 소스 저장</button>
    </div>

    <!-- ── Ollama AI 모델 ──────────────────────────────────── -->
    <div class="page" id="page-ollama">
      <div class="ollama-status">
        <div class="ollama-dot" id="ollama-dot" style="background:var(--muted2)"></div>
        <div>
          <div style="font-size:13px;font-weight:700" id="ollama-status-text">연결 확인 중...</div>
          <div style="font-size:11px;color:var(--muted)" id="ollama-models-text"></div>
        </div>
        <div class="spacer"></div>
        <button class="btn sm" onclick="testOllama()">연결 테스트</button>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        <div class="info-box success">
          <strong>✅ Ollama 없이 (기본 모드)</strong><br>
          · yfinance + API 기반 규칙 분석<br>
          · 즉각 응답 (5~15초)<br>
          · 인터넷만 있으면 동작
        </div>
        <div class="info-box">
          <strong>🤖 Ollama 사용 시 추가 기능</strong><br>
          · 뉴스/공시 문장 심화 감성 분석<br>
          · 브리핑 자연어 다듬기 (polish)<br>
          · 임베딩 기반 중복 뉴스 제거<br>
          · 설치: <a href="https://ollama.com" style="color:var(--blue)" target="_blank">ollama.com</a> → <code style="font-size:11px">ollama pull qwen3:8b</code>
        </div>
      </div>

      <div class="form-section">
        <div class="form-section-title">Ollama 연결 설정</div>
        <div class="form-grid">
          <div class="form-row">
            <label>Ollama 서버 주소</label>
            <input class="inp" id="cfg-ollama-host" placeholder="http://127.0.0.1:11434">
          </div>
          <div class="form-row">
            <label>채팅 모델</label>
            <input class="inp" id="cfg-ollama-model" placeholder="qwen3:8b">
            <div class="hint">추천: qwen3:8b (8GB RAM) / qwen3:4b (4GB RAM)</div>
          </div>
          <div class="form-row">
            <label>임베딩 모델</label>
            <input class="inp" id="cfg-ollama-embed" placeholder="qwen3-embedding:0.6b">
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn primary" onclick="saveOllama()">💾 저장</button>
          <button class="btn" onclick="testOllama()">🔗 연결 테스트</button>
        </div>
        <div id="ollama-test-result" style="margin-top:8px"></div>
      </div>

      <div class="form-section">
        <div class="form-section-title">임베딩 기반 중복 제거 설정</div>
        <div class="toggle-row">
          <div class="toggle-info">
            <div class="t-title">임베딩 중복 제거 사용</div>
            <div class="t-desc">유사 뉴스를 자동으로 합쳐서 노이즈를 줄입니다 (Ollama 필요)</div>
          </div>
          <label class="toggle"><input type="checkbox" id="cfg-embed-dedupe"><span class="slider"></span></label>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<div class="toast" id="toast"></div>

<script>
// ─────────────────────────────────────────────────────────────
// 상태
// ─────────────────────────────────────────────────────────────
let curMkt = 'KR';
let curBriefMkt = 'KR';
let screenerLoaded = false;
let configCache = {};
let _screenerCache = {data:null, market:null, ts:0};  // 5분 캐시

// ─────────────────────────────────────────────────────────────
// 네비게이션
// ─────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  market:'시장 개요', screener:'종목 스크리너', analysis:'종목 상세 분석',
  briefing:'4H 브리핑', telegram:'텔레그램 설정', scheduler:'4H 스케줄러',
  datasource:'데이터 소스', ollama:'AI 모델 (Ollama)'
};
let curPage = 'market';

function nav(page) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById('nav-'+page)?.classList.add('active');
  document.getElementById('page-'+page)?.classList.add('active');
  document.getElementById('page-title').textContent = PAGE_TITLES[page] || page;
  curPage = page;
  // 페이지별 초기 로드
  if(page==='screener' && !screenerLoaded) loadScreener();
  if(page==='briefing') { if(document.getElementById('briefing-body').querySelector('.loading')) loadBriefing(curBriefMkt); }
  if(page==='telegram') loadTelegramConfig();
  if(page==='datasource') loadDatasources();
  if(page==='ollama') { loadOllamaConfig(); checkOllama(); }
  if(page==='scheduler') loadSchedulerStatus();
}

// ─────────────────────────────────────────────────────────────
// 시장 선택
// ─────────────────────────────────────────────────────────────
function setMkt(mkt) {
  if(curMkt === mkt) return;
  curMkt = mkt;
  ['kr','us','all'].forEach(m => document.getElementById('btn-'+m).classList.toggle('active', m===mkt.toLowerCase()));
  // 분석 마켓 셀렉터 동기화 (ALL → US 기본값, 분석 페이지 아닐 때만)
  const aMkt = document.getElementById('a-mkt');
  if(aMkt && curPage !== 'analysis') aMkt.value = mkt==='ALL'?'US':mkt;
  // 시장 변경 시 캐시 무효화
  _screenerCache = {data:null, market:null, ts:0};
  screenerLoaded = false;
  if(curPage==='market') loadMarket();
  else if(curPage==='screener') loadScreener();
}

function refreshCurrent() {
  if(curPage==='market') loadMarket();
  else if(curPage==='screener') loadScreener();
  else if(curPage==='briefing') loadBriefing(curBriefMkt);
  else if(curPage==='analysis') { const sym=document.getElementById('a-ticker').value.trim(); if(sym) doAnalysis(); }
  else if(curPage==='ollama') checkOllama();
  else if(curPage==='scheduler') loadSchedulerStatus();
}

// ─────────────────────────────────────────────────────────────
// 포맷 유틸
// ─────────────────────────────────────────────────────────────
function fmtChg(v, unit='%', digits=2) {
  if(v==null) return '<span class="neu">—</span>';
  const cls=v>0?'up':v<0?'dn':'neu', sign=v>0?'+':'';
  return `<span class="${cls}">${sign}${v.toFixed(digits)}${unit}</span>`;
}
function fmtPrice(v, cur) {
  if(v==null) return '—';
  return cur==='KRW' ? Math.round(v).toLocaleString()+'원' : '$'+v.toFixed(2);
}
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function sigTag(s) {
  const m={STRONG_WATCH:['강력관찰','tag-green'],WATCH:['관찰','tag-yellow'],NEUTRAL:['중립','tag-blue'],AVOID:['회피','tag-red']};
  const [label,cls] = m[s]||['중립','tag-blue'];
  return `<span class="sig ${cls}">${label}</span>`;
}
function scoreBar(v) {
  const color = v>=72?'var(--green)':v>=58?'var(--yellow)':v>=42?'var(--blue)':'var(--red)';
  return `<div class="score-wrap"><span class="score-num" style="color:${color}">${v.toFixed(0)}</span><div class="score-track"><div class="score-fill" style="width:${v}%;background:${color}"></div></div></div>`;
}

// ─────────────────────────────────────────────────────────────
// 시장 개요 로드
// ─────────────────────────────────────────────────────────────
async function loadMarket() {
  document.getElementById('macro-body').innerHTML = '<div class="loading"><span class="spinner"></span>수집 중...</div>';
  document.getElementById('index-body').innerHTML = '<div class="loading"><span class="spinner"></span>수집 중...</div>';
  document.getElementById('top-picks').innerHTML = '<div class="loading"><span class="spinner"></span>스크리닝 중...</div>';
  const [macro] = await Promise.all([fetchMacro()]);
  renderMacro(macro);
  loadTopPicks();
}

async function fetchMacro() {
  try { return await (await fetch('/api/macro')).json(); }
  catch(e){ return {error:e.message}; }
}

function renderMacro(d) {
  if(d.error) { document.getElementById('macro-body').innerHTML=`<div class="err-msg">${d.error}</div>`; return; }
  const rows = [
    {label:'VIX', val:d.vix?.toFixed(1)||'—', chg:fmtChg(d.vix_chg,'%')},
    {label:'미국 10Y', val:d.us10y!=null?d.us10y.toFixed(2)+'%':'—', chg:fmtChg(d.us10y_chg,'bp')},
    {label:'USD/KRW', val:d.usd_krw!=null?Math.round(d.usd_krw).toLocaleString()+'원':'—', chg:fmtChg(d.usd_krw_chg,'%')},
    {label:'Gold', val:d.gold_price!=null?'$'+Math.round(d.gold_price):'—', chg:fmtChg(d.gold_chg,'%')},
    {label:'WTI', val:d.wti_price!=null?'$'+d.wti_price.toFixed(1):'—', chg:fmtChg(d.wti_chg,'%')},
    {label:'DXY', val:d.dxy?.toFixed(1)||'—', chg:fmtChg(d.dxy_chg,'%')},
  ];
  const regMap={'위험선호':'tag-green','위험회피':'tag-red','중립':'tag-blue'};
  const html = rows.map(r=>`<div class="macro-row">
    <span class="macro-label">${r.label}</span>
    <span class="macro-val">${r.val}</span>
    <span class="macro-chg">${r.chg}</span>
  </div>`).join('')
  + `<div class="regime-bar ${regMap[d.regime]||'tag-blue'}" style="margin-top:10px">레짐: ${d.regime||'중립'}</div>`;
  document.getElementById('macro-body').innerHTML = html;

  // 지수 변화
  const idx = [
    {label:'S&P 500', chg:d.sp500_chg},
    {label:'KOSPI', chg:d.kospi_chg},
    {label:'Gold', chg:d.gold_chg},
    {label:'WTI', chg:d.wti_chg},
    {label:'USD/KRW', chg:d.usd_krw_chg},
    {label:'DXY', chg:d.dxy_chg},
  ];
  const idxHtml = idx.filter(r=>r.chg!=null).map(r=>`<div class="macro-row">
    <span class="macro-label">${r.label}</span>
    <span class="macro-chg">${fmtChg(r.chg,'%')}</span>
  </div>`).join('') + (d.interpretations||[]).slice(0,3).map(s=>`<div style="font-size:11px;color:var(--muted);padding:4px 0;border-bottom:1px solid rgba(48,54,61,.5)">${s}</div>`).join('');
  document.getElementById('index-body').innerHTML = idxHtml || '<div class="empty">데이터 없음</div>';
}

async function loadTopPicks() {
  try {
    const now = Date.now();
    let quotes;
    // 5분 내 같은 시장 캐시 재사용
    if(_screenerCache.data && _screenerCache.market===curMkt && now-_screenerCache.ts < 300000) {
      quotes = _screenerCache.data;
    } else {
      const r = await fetch(`/api/screener?market=${curMkt}`);
      const d = await r.json();
      quotes = d.quotes || [];
      _screenerCache = {data: quotes, market: curMkt, ts: now};
    }
    const top = quotes.slice(0,6);
    if(!top.length){ document.getElementById('top-picks').innerHTML='<div class="empty">스크리닝 결과 없음</div>'; return; }
    const html = `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
      ${top.map(q=>`<div style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:10px 12px;cursor:pointer" onclick="goAnalysis('${q.symbol}','${q.market}')">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
          <span style="font-weight:700;color:var(--blue)">${esc(q.symbol)}</span>
          ${sigTag(q.signal)}
        </div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(q.name||'')}</div>
        <div style="display:flex;justify-content:space-between">
          <span style="font-size:13px;font-weight:700">${fmtPrice(q.price,q.currency)}</span>
          <span style="font-size:13px">${fmtChg(q.chg_1d,'%')}</span>
        </div>
        <div style="margin-top:6px">${scoreBar(q.score)}</div>
      </div>`).join('')}
    </div>`;
    document.getElementById('top-picks').innerHTML = html;
  } catch(e) {
    document.getElementById('top-picks').innerHTML = `<div class="err-msg">${esc(e.message)}</div>`;
  }
}

// ─────────────────────────────────────────────────────────────
// 스크리너
// ─────────────────────────────────────────────────────────────
async function loadScreener() {
  screenerLoaded = false;
  document.getElementById('screener-wrap').innerHTML='<div class="loading"><span class="spinner"></span>스크리닝 중 (최대 30초)...</div>';
  try {
    const now = Date.now();
    let quotes, market;
    // 5분 내 같은 시장 캐시 재사용
    if(_screenerCache.data && _screenerCache.market===curMkt && now-_screenerCache.ts < 300000) {
      quotes = _screenerCache.data;
      market = _screenerCache.market;
    } else {
      const r = await fetch(`/api/screener?market=${curMkt}`);
      const d = await r.json();
      quotes = d.quotes || [];
      market = d.market || curMkt;
      _screenerCache = {data: quotes, market: curMkt, ts: now};
    }
    screenerLoaded = true;
    document.getElementById('screener-meta').textContent=`${market} · ${quotes.length}개 종목 · ${new Date().toLocaleTimeString('ko-KR')} 기준`;
    renderScreenerTable(quotes);
  } catch(e){
    document.getElementById('screener-wrap').innerHTML=`<div class="loading err-msg">${esc(e.message)}</div>`;
  }
}
function renderScreenerTable(quotes) {
  if(!quotes.length){ document.getElementById('screener-wrap').innerHTML='<div class="empty">결과 없음</div>'; return; }
  const rows = quotes.map(q=>`<tr onclick="goAnalysis('${esc(q.symbol)}','${esc(q.market)}')">
    <td class="sym">${esc(q.symbol)}</td>
    <td class="name-cell">${esc(q.name||'')}</td>
    <td>${fmtPrice(q.price,q.currency)}</td>
    <td>${fmtChg(q.chg_1d,'%')}</td>
    <td>${fmtChg(q.chg_1w,'%')}</td>
    <td>${q.rsi_14!=null?q.rsi_14.toFixed(0):'—'}</td>
    <td>${q.pe_trailing!=null?q.pe_trailing.toFixed(1):'—'}</td>
    <td>${scoreBar(q.score)}</td>
    <td>${sigTag(q.signal)}</td>
  </tr>`).join('');
  document.getElementById('screener-wrap').innerHTML=`<table class="tbl">
    <thead><tr><th>종목</th><th>이름</th><th>현재가</th><th>1D%</th><th>1W%</th><th>RSI</th><th>PER</th><th>점수</th><th>신호</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function goAnalysis(sym, mkt) {
  document.getElementById('a-ticker').value = sym;
  document.getElementById('a-mkt').value = mkt||'US';
  nav('analysis');
  doAnalysis();
}

// ─────────────────────────────────────────────────────────────
// 종목 상세 분석
// ─────────────────────────────────────────────────────────────
async function doAnalysis() {
  const sym = document.getElementById('a-ticker').value.trim().toUpperCase();
  const mkt = document.getElementById('a-mkt').value;
  if(!sym) return;
  document.getElementById('analysis-result').innerHTML='<div class="loading"><span class="spinner"></span>분석 중 (10~20초)...</div>';
  try {
    const r = await fetch(`/api/snapshot/${sym}?market=${mkt}`);
    const d = await r.json();
    renderAnalysis(d);
  } catch(e){
    document.getElementById('analysis-result').innerHTML=`<div class="err-msg">${e.message}</div>`;
  }
}
function renderAnalysis(d) {
  if(d.error && !d.price){ document.getElementById('analysis-result').innerHTML=`<div class="err-msg">${d.error}</div>`; return; }
  const chgCls = v => v==null?'neu':v>0?'up':v<0?'dn':'neu';
  const cards=[
    {label:'현재가', value:fmtPrice(d.price,d.currency), sub:d.name||''},
    {label:'1일 변동', value:d.chg_1d!=null?`${d.chg_1d>0?'+':''}${d.chg_1d.toFixed(2)}%`:'—', cls:chgCls(d.chg_1d), sub:`1W: ${d.chg_1w!=null?(d.chg_1w>0?'+':'')+d.chg_1w.toFixed(2)+'%':'—'}`},
    {label:'투자 스코어', value:d.total_score!=null?d.total_score.toFixed(0):'—', sub:d.grade||''},
    {label:'RSI(14)', value:d.rsi!=null?d.rsi.toFixed(1):'—', sub:''},
    {label:'PER / PBR', value:d.pe_trailing!=null?d.pe_trailing.toFixed(1):'—', sub:'PBR: '+(d.pb!=null?d.pb.toFixed(2):'—')},
    {label:'섹터', value:d.sector||'—', sub:d.industry||''},
  ];
  const kpiHtml = cards.map(c=>`<div class="detail-kpi">
    <div class="label">${c.label}</div>
    <div class="value ${c.cls||''}">${c.value}</div>
    <div class="sub">${c.sub}</div>
  </div>`).join('');
  const report = d.report?`<div class="report-box">${esc(d.report)}</div>`:'';
  document.getElementById('analysis-result').innerHTML=`<div class="detail-grid">${kpiHtml}</div>${report}`;
}

// ─────────────────────────────────────────────────────────────
// 4H 브리핑
// ─────────────────────────────────────────────────────────────
async function loadBriefing(mkt) {
  curBriefMkt = mkt;
  ['kr','us'].forEach(m=>document.getElementById('br-'+m).classList.toggle('active',m===mkt.toLowerCase()));
  document.getElementById('briefing-body').innerHTML='<div class="loading"><span class="spinner"></span>4H 브리핑 생성 중 (1~2분 소요)...</div>';
  try {
    const r = await fetch(`/api/briefing?market=${mkt}`);
    const d = await r.json();
    document.getElementById('briefing-body').innerHTML = esc(d.report||d.error||'결과 없음');
  } catch(e){
    document.getElementById('briefing-body').innerHTML=`<div class="err-msg">${e.message}</div>`;
  }
}

// ─────────────────────────────────────────────────────────────
// 텔레그램 설정
// ─────────────────────────────────────────────────────────────
async function loadTelegramConfig() {
  try {
    const d = await (await fetch('/api/config')).json();
    configCache = d;
    document.getElementById('cfg-bot-token').value = d.TELEGRAM_BOT_TOKEN||'';
    document.getElementById('cfg-chat-id').value = d.TELEGRAM_BOT_TARGET_CHAT_ID||'';
    document.getElementById('cfg-api-id').value = d.TELEGRAM_API_ID||'';
    document.getElementById('cfg-api-hash').value = d.TELEGRAM_API_HASH||'';
    document.getElementById('cfg-phone').value = d.TELEGRAM_PHONE||'';
    document.getElementById('cfg-chats').value = d.TELEGRAM_SOURCE_CHATS||'';
  } catch(e){}
}
async function saveTelegram() {
  const updates = {
    TELEGRAM_BOT_TOKEN: document.getElementById('cfg-bot-token').value.trim(),
    TELEGRAM_BOT_TARGET_CHAT_ID: document.getElementById('cfg-chat-id').value.trim(),
    TELEGRAM_SEND_MODE: 'bot',
  };
  await saveConfig(updates);
  toast('텔레그램 봇 설정 저장됨','ok');
}
async function saveTelegramAdv() {
  const updates = {
    TELEGRAM_API_ID: document.getElementById('cfg-api-id').value.trim(),
    TELEGRAM_API_HASH: document.getElementById('cfg-api-hash').value.trim(),
    TELEGRAM_PHONE: document.getElementById('cfg-phone').value.trim(),
    TELEGRAM_SOURCE_CHATS: document.getElementById('cfg-chats').value.trim(),
  };
  await saveConfig(updates);
  toast('채널 수집 설정 저장됨','ok');
}
async function testTelegram() {
  const token = document.getElementById('cfg-bot-token').value.trim();
  const chatId = document.getElementById('cfg-chat-id').value.trim();
  if(!token||!chatId){ toast('토큰과 Chat ID를 먼저 입력하세요','err'); return; }
  document.getElementById('tg-result').innerHTML='<span class="spinner"></span>전송 중...';
  try {
    const r = await fetch('/api/telegram/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bot_token:token,chat_id:chatId})});
    const d = await r.json();
    document.getElementById('tg-result').innerHTML=`<span class="${d.ok?'up':'dn'}">${d.message}</span>`;
    toast(d.message, d.ok?'ok':'err');
  } catch(e){ document.getElementById('tg-result').innerHTML=`<span class="dn">${e.message}</span>`; }
}

// ─────────────────────────────────────────────────────────────
// 스케줄러
// ─────────────────────────────────────────────────────────────
async function loadSchedulerStatus() {
  try {
    const d = await (await fetch('/api/scheduler/status')).json();
    const running = d.running;
    document.getElementById('sched-toggle').checked = running;
    document.getElementById('sched-status-text').textContent = running ? '🟢 실행 중' : '⭕ 중지됨';
    document.getElementById('sched-status-text').style.color = running ? 'var(--green)' : 'var(--muted)';
    document.getElementById('sched-next').textContent = running && d.next_run ? '다음 실행: ' + new Date(d.next_run).toLocaleString('ko-KR') : '스케줄러 꺼짐';
    document.getElementById('dot-sched').className = 'dot '+(running?'on':'off');
    document.getElementById('label-sched').textContent = '4H 스케줄러 '+(running?'ON':'OFF');
    if(d.market) document.getElementById('sched-market').value=d.market;
    if(d.run_count) document.getElementById('sched-history').textContent=`실행 횟수: ${d.run_count}회  마지막: ${d.last_run?new Date(d.last_run).toLocaleString('ko-KR'):'없음'}`;
  } catch(e){}
}
async function toggleScheduler() {
  const on = document.getElementById('sched-toggle').checked;
  const market = document.getElementById('sched-market').value;
  const interval = parseInt(document.getElementById('sched-interval').value);
  try {
    const ep = on ? '/api/scheduler/start' : '/api/scheduler/stop';
    const r = await fetch(ep, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({market,interval_h:interval})});
    const d = await r.json();
    toast(d.message, d.ok?'ok':'err');
    setTimeout(loadSchedulerStatus, 500);
  } catch(e){ toast(e.message,'err'); }
}
async function schedRunNow() {
  try {
    const r = await fetch('/api/scheduler/run-now', {method:'POST'});
    const d = await r.json();
    toast(d.message,'info');
  } catch(e){ toast(e.message,'err'); }
}

// ─────────────────────────────────────────────────────────────
// 데이터 소스
// ─────────────────────────────────────────────────────────────
const DATA_SOURCES = [
  {key:'YFINANCE', label:'Yahoo Finance', desc:'주가·기술지표 (무료, 항상 활성)', always:true},
  {key:'FINNHUB', label:'Finnhub', desc:'뉴스/실적 데이터 (무료 플랜 가능)', apiKey:'FINNHUB_API_KEY', link:'https://finnhub.io'},
  {key:'OPENDART', label:'OpenDART', desc:'한국 전자공시 (DART 인증키 필요)', apiKey:'OPENDART_API_KEY', link:'https://opendart.fss.or.kr'},
  {key:'NAVER', label:'Naver 뉴스', desc:'네이버 뉴스 검색', apiKey:'NAVER_CLIENT_ID', link:'https://developers.naver.com'},
  {key:'FRED', label:'FRED', desc:'미국 연준 매크로 지표', apiKey:'FRED_API_KEY', link:'https://fred.stlouisfed.org'},
  {key:'ECOS', label:'ECOS (한국은행)', desc:'한국 경제 통계', apiKey:'ECOS_API_KEY', link:'https://ecos.bok.or.kr'},
  {key:'ALPHAVANTAGE', label:'Alpha Vantage', desc:'주가·기술지표 보완', apiKey:'ALPHAVANTAGE_API_KEY', link:'https://www.alphavantage.co'},
  {key:'NEWSAPI', label:'NewsAPI', desc:'영문 뉴스 (100 req/day 무료)', apiKey:'NEWSAPI_KEY', link:'https://newsapi.org'},
  {key:'FMP', label:'FMP (Financial Modeling Prep)', desc:'재무 데이터·실적', apiKey:'FMP_API_KEY', link:'https://site.financialmodelingprep.com'},
];
async function loadDatasources() {
  try {
    const d = await (await fetch('/api/config')).json();
    configCache = {...configCache,...d};
    const html = DATA_SOURCES.map(src=>{
      const enabled = d[src.key+'_ENABLED']==='true';
      const hasKey = src.apiKey ? !!d[src.apiKey] && d[src.apiKey]!=='●●●●●●●●' && d[src.apiKey]!=='' : true;
      return `<div class="toggle-row">
        <div class="toggle-info">
          <div class="t-title">${src.label} ${src.always?'<span style="font-size:11px;color:var(--muted)">(항상 활성)</span>':''}</div>
          <div class="t-desc">${src.desc}${src.link?` · <a href="${src.link}" target="_blank" style="color:var(--blue)">키 발급</a>`:''}</div>
          ${src.apiKey?`<div style="margin-top:6px"><input class="inp" id="key-${src.key}" value="${d[src.apiKey]||''}" placeholder="${src.apiKey}" style="font-size:12px;padding:5px 9px;max-width:280px"></div>`:''}
        </div>
        <label class="toggle" ${src.always?'style="opacity:.4;pointer-events:none"':''}>
          <input type="checkbox" id="toggle-${src.key}" ${enabled||src.always?'checked':''}><span class="slider"></span>
        </label>
      </div>`;
    }).join('');
    document.getElementById('datasource-list').innerHTML = html;
  } catch(e){ document.getElementById('datasource-list').innerHTML=`<div class="err-msg">${e.message}</div>`; }
}
async function saveDatasources() {
  const updates = {};
  DATA_SOURCES.forEach(src=>{
    if(!src.always){
      const el = document.getElementById('toggle-'+src.key);
      if(el) updates[src.key+'_ENABLED'] = el.checked?'true':'false';
    }
    if(src.apiKey){
      const keyEl = document.getElementById('key-'+src.key);
      if(keyEl && keyEl.value && keyEl.value!=='●●●●●●●●') updates[src.apiKey] = keyEl.value.trim();
    }
  });
  await saveConfig(updates);
  toast('데이터 소스 설정 저장됨','ok');
}

// ─────────────────────────────────────────────────────────────
// Ollama
// ─────────────────────────────────────────────────────────────
async function loadOllamaConfig() {
  try {
    const d = await (await fetch('/api/config')).json();
    document.getElementById('cfg-ollama-host').value = d.OLLAMA_HOST||'http://127.0.0.1:11434';
    document.getElementById('cfg-ollama-model').value = d.OLLAMA_CHAT_MODEL||'qwen3:8b';
    document.getElementById('cfg-ollama-embed').value = d.OLLAMA_EMBED_MODEL||'qwen3-embedding:0.6b';
    document.getElementById('cfg-embed-dedupe').checked = d.EMBEDDING_DEDUPE==='true';
  } catch(e){}
}
async function checkOllama() {
  document.getElementById('ollama-status-text').textContent='연결 확인 중...';
  try {
    const r = await fetch('/api/ollama/status');
    const d = await r.json();
    const dot = document.getElementById('ollama-dot');
    if(d.ok){
      dot.style.background='var(--green)';
      document.getElementById('ollama-status-text').textContent='✅ 연결됨';
      document.getElementById('ollama-models-text').textContent='사용 가능 모델: '+(d.models||[]).join(', ');
      document.getElementById('dot-ollama').className='dot on';
      document.getElementById('label-ollama').textContent='Ollama 연결됨';
    } else {
      dot.style.background='var(--muted2)';
      document.getElementById('ollama-status-text').textContent='⭕ 연결 안됨 (규칙 기반 모드)';
      document.getElementById('ollama-models-text').textContent=d.message||'Ollama 서버 없음';
      document.getElementById('dot-ollama').className='dot';
      document.getElementById('label-ollama').textContent='Ollama 미연결';
    }
  } catch(e){}
}
async function testOllama() {
  const host = document.getElementById('cfg-ollama-host').value.trim();
  const model = document.getElementById('cfg-ollama-model').value.trim();
  document.getElementById('ollama-test-result').innerHTML='<span class="spinner"></span>테스트 중...';
  try {
    const r = await fetch('/api/ollama/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host,model})});
    const d = await r.json();
    document.getElementById('ollama-test-result').innerHTML=`<span class="${d.ok?'up':'dn'}">${d.message}${d.has_target===false?' · 모델 없음 (ollama pull '+model+')':''}</span>`;
  } catch(e){ document.getElementById('ollama-test-result').innerHTML=`<span class="dn">${e.message}</span>`; }
}
async function saveOllama() {
  const updates={
    OLLAMA_HOST: document.getElementById('cfg-ollama-host').value.trim(),
    OLLAMA_CHAT_MODEL: document.getElementById('cfg-ollama-model').value.trim(),
    OLLAMA_EMBED_MODEL: document.getElementById('cfg-ollama-embed').value.trim(),
    EMBEDDING_DEDUPE: document.getElementById('cfg-embed-dedupe').checked?'true':'false',
  };
  await saveConfig(updates);
  toast('Ollama 설정 저장됨','ok');
  checkOllama();
}

// ─────────────────────────────────────────────────────────────
// 공통 설정 저장
// ─────────────────────────────────────────────────────────────
async function saveConfig(updates) {
  try {
    await fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(updates)});
  } catch(e){ toast('저장 실패: '+e.message,'err'); }
}

// ─────────────────────────────────────────────────────────────
// 토스트
// ─────────────────────────────────────────────────────────────
let _toastTimer;
function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type} show`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(()=>el.classList.remove('show'), 3000);
}

// ─────────────────────────────────────────────────────────────
// 초기 로드
// ─────────────────────────────────────────────────────────────
window.addEventListener('load', () => {
  loadMarket();
  loadSchedulerStatus();
  checkOllama();
});
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI 앱
# ─────────────────────────────────────────────────────────────────────────────

def _new_token() -> str:
    return secrets.token_hex(32)


def _is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


def _create_session(long_lived: bool = False) -> str:
    # 오래된 세션 정리
    now = time.time()
    expired = [t for t, exp in _sessions.items() if exp < now]
    for t in expired:
        _sessions.pop(t, None)
    # 최대 세션 수 초과 시 가장 오래된 것부터 제거 (마스터 세션은 보호)
    if len(_sessions) >= _SESSION_MAX:
        non_master = sorted(
            [t for t, exp in _sessions.items() if exp - now < _MASTER_TTL / 2],
            key=lambda t: _sessions[t],
        )
        for t in non_master[:len(_sessions) - _SESSION_MAX + 1]:
            _sessions.pop(t, None)
    token = _new_token()
    _sessions[token] = now + (_MASTER_TTL if long_lived else _SESSION_TTL)
    return token


def create_app(settings_path: str | Path | None = None) -> Any:
    if not _FASTAPI_AVAILABLE:
        raise ImportError(
            "fastapi와 uvicorn이 필요합니다.\n  uv add fastapi 'uvicorn[standard]'"
        )

    from tele_quant.settings import Settings
    cfg = Settings()

    # 비밀번호 설정 여부 확인 (없으면 인증 비활성화)
    _password: str = getattr(cfg, "dashboard_password", "") or ""
    _master_key: str = getattr(cfg, "dashboard_master_key", "") or ""
    _auth_enabled: bool = bool(_password) or bool(_master_key)

    if _master_key:
        log.info("대시보드 마스터키 활성화 — 마스터키: 무제한 세션 / 일반 비밀번호: 24시간 세션")
    elif _auth_enabled:
        log.info("대시보드 비밀번호 인증 활성화됨 (마스터키 미설정)")
    else:
        log.info("대시보드 비밀번호 미설정 — 인증 없이 접근 허용")

    app = FastAPI(title="Tele Quant Dashboard", docs_url=None, redoc_url=None)

    # ── 인증 미들웨어 ────────────────────────────────────────────────────────
    _OPEN_PATHS = {"/login", "/api/health"}

    class _AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # type: ignore[override]
            if not _auth_enabled or request.url.path in _OPEN_PATHS:
                return await call_next(request)
            token = request.cookies.get("tq_session")
            if not _is_valid_session(token):
                if request.url.path.startswith("/api/"):
                    return JSONResponse({"ok": False, "error": "인증 필요"}, status_code=401)
                return RedirectResponse("/login", status_code=302)
            return await call_next(request)

    app.add_middleware(_AuthMiddleware)

    # ── 로그인 / 로그아웃 ──────────────────────────────────────────────────
    @app.get("/login")
    async def login_page() -> HTMLResponse:
        return HTMLResponse(_LOGIN_HTML)

    @app.post("/login")
    async def login_post(req: Request) -> JSONResponse:
        try:
            data: dict = await req.json()
        except Exception:
            data = {}
        if not _auth_enabled:
            return JSONResponse({"ok": True})
        pw: str = data.get("password", "") or ""
        # 타이밍 공격 방지: 두 비교를 항상 모두 수행
        is_master = bool(_master_key) and secrets.compare_digest(pw, _master_key)
        is_user   = bool(_password)   and secrets.compare_digest(pw, _password)
        if is_master or is_user:
            token = _create_session(long_lived=is_master)
            max_age = int(_MASTER_TTL if is_master else _SESSION_TTL)
            resp = JSONResponse({"ok": True})
            resp.set_cookie(
                key="tq_session",
                value=token,
                max_age=max_age,
                httponly=True,
                samesite="strict",
            )
            return resp
        return JSONResponse({"ok": False}, status_code=401)

    @app.get("/logout")
    async def logout(req: Request) -> RedirectResponse:
        token = req.cookies.get("tq_session")
        _sessions.pop(token, None)
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie("tq_session")
        return resp

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _HTML

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse({"ok": True, "service": "tele-quant-dashboard"})

    # ── 매크로 ────────────────────────────────────────────────────────────────
    @app.get("/api/macro")
    async def api_macro() -> JSONResponse:
        try:
            from tele_quant.macro_pulse import fetch_macro_snapshot
            s = fetch_macro_snapshot()
            return JSONResponse({
                "fetched_at": s.fetched_at.strftime("%Y-%m-%d %H:%M UTC"),
                "vix": s.vix, "vix_chg": s.vix_chg,
                "us10y": s.us10y, "us10y_chg": s.us10y_chg,
                "usd_krw": s.usd_krw, "usd_krw_chg": s.usd_krw_chg,
                "sp500_chg": s.sp500_chg, "kospi_chg": s.kospi_chg,
                "gold_price": s.gold_price, "gold_chg": s.gold_chg,
                "wti_price": s.wti_price, "wti_chg": s.wti_chg,
                "dxy": s.dxy, "dxy_chg": s.dxy_chg,
                "regime": s.regime, "interpretations": s.interpretations,
            })
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── 스크리너 ──────────────────────────────────────────────────────────────
    @app.get("/api/screener")
    async def api_screener(market: str = "KR") -> JSONResponse:
        try:
            syms = _watchlist_symbols(cfg, market.upper())
            from tele_quant.dashboard._screener import run_screener
            quotes = run_screener(syms)
            return JSONResponse({
                "market": market.upper(), "count": len(quotes),
                "quotes": [_q2d(q) for q in quotes],
            })
        except Exception as exc:
            return JSONResponse({"error": str(exc), "quotes": []}, status_code=500)

    # ── 종목 스냅샷 ───────────────────────────────────────────────────────────
    @app.get("/api/snapshot/{ticker}")
    async def api_snapshot(ticker: str, market: str = "US") -> JSONResponse:
        try:
            from tele_quant.db import Store
            from tele_quant.stock_snapshot import build_stock_snapshot, format_stock_snapshot
            store = Store(cfg.sqlite_path)
            snap = build_stock_snapshot(ticker.upper(), market.upper(), store=store, deep=False)
            return JSONResponse({
                "symbol": snap.symbol, "name": snap.name, "market": snap.market,
                "price": snap.close,
                "currency": "KRW" if snap.market == "KR" else "USD",
                "chg_1d": snap.price_change_1d, "chg_1w": snap.price_change_1w,
                "rsi": snap.daily_rsi, "pe_trailing": snap.pe_trailing, "pb": snap.pb,
                "roe": snap.roe, "sector": snap.sector, "industry": snap.industry,
                "total_score": snap.total_score, "grade": snap.grade,
                "report": format_stock_snapshot(snap), "error": snap.error,
            })
        except Exception as exc:
            return JSONResponse({"symbol": ticker, "error": str(exc)}, status_code=500)

    # ── 브리핑 ────────────────────────────────────────────────────────────────
    @app.get("/api/briefing")
    async def api_briefing(market: str = "KR") -> JSONResponse:
        try:
            from pathlib import Path as _P

            from tele_quant.db import Store
            mkt = market.upper()
            store = Store(_P(cfg.sqlite_path))
            use_advisory = getattr(cfg, "advisory_only_mode", True)
            if use_advisory:
                from tele_quant.advisor_4h import run_4h_advisory
                report = run_4h_advisory(mkt, store, cfg, top_n=5)
            else:
                from tele_quant.briefing import run_4h_briefing
                report = run_4h_briefing(mkt, store, cfg, top_n=5)
            return JSONResponse({"market": mkt, "report": report or "(결과 없음)"})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── 설정 읽기/쓰기 ────────────────────────────────────────────────────────
    @app.get("/api/config")
    async def api_config_get() -> JSONResponse:
        from tele_quant.dashboard._config import read_config
        return JSONResponse(read_config(mask_secrets=True))

    @app.post("/api/config")
    async def api_config_post(body: dict) -> JSONResponse:
        from tele_quant.dashboard._config import update_config
        update_config(body)
        return JSONResponse({"ok": True})

    # ── 텔레그램 테스트 ───────────────────────────────────────────────────────
    @app.post("/api/telegram/test")
    async def api_telegram_test(body: dict) -> JSONResponse:
        from tele_quant.dashboard._config import test_telegram
        result = await test_telegram(body.get("bot_token",""), body.get("chat_id",""))
        return JSONResponse(result)

    # ── Ollama 상태 / 테스트 ──────────────────────────────────────────────────
    @app.get("/api/ollama/status")
    async def api_ollama_status() -> JSONResponse:
        from tele_quant.dashboard._config import test_ollama
        host = getattr(cfg, "ollama_host", "http://127.0.0.1:11434")
        model = getattr(cfg, "ollama_chat_model", "qwen3:8b")
        result = await test_ollama(host, model)
        return JSONResponse(result)

    @app.post("/api/ollama/test")
    async def api_ollama_test(body: dict) -> JSONResponse:
        from tele_quant.dashboard._config import test_ollama
        result = await test_ollama(body.get("host","http://127.0.0.1:11434"), body.get("model","qwen3:8b"))
        return JSONResponse(result)

    # ── 스케줄러 ─────────────────────────────────────────────────────────────
    @app.get("/api/scheduler/status")
    async def api_sched_status() -> JSONResponse:
        from tele_quant.dashboard._scheduler import get_status
        return JSONResponse(get_status())

    @app.post("/api/scheduler/start")
    async def api_sched_start(body: dict) -> JSONResponse:
        from tele_quant.dashboard._scheduler import start
        return JSONResponse(start(body.get("market","KR"), body.get("interval_h",4)))

    @app.post("/api/scheduler/stop")
    async def api_sched_stop() -> JSONResponse:
        from tele_quant.dashboard._scheduler import stop
        return JSONResponse(stop())

    @app.post("/api/scheduler/run-now")
    async def api_sched_run_now() -> JSONResponse:
        from tele_quant.dashboard._scheduler import run_now
        return JSONResponse(run_now())

    return app


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _watchlist_symbols(cfg: Any, market: str) -> list[str]:
    from tele_quant.watchlist import load_watchlist
    wl_path = getattr(cfg, "watchlist_path", "config/watchlist.yml")
    wl = load_watchlist(wl_path)
    all_syms = list(wl.watchlist_symbols()) if wl else [
        "005930.KS","000660.KS","035420.KS","005380.KS","012450.KS","064350.KS",
        "329180.KS","196170.KQ","068270.KS","454910.KS",
        "NVDA","MSFT","AAPL","GOOGL","AMZN","META","AMD","AVGO","PLTR","MU",
    ]
    if market == "KR":
        return [s for s in all_syms if s.endswith((".KS", ".KQ"))]
    if market == "US":
        return [s for s in all_syms if not s.endswith((".KS", ".KQ"))]
    return all_syms


def _q2d(q: Any) -> dict:
    return {
        "symbol": q.symbol, "name": q.name, "market": q.market,
        "price": q.price, "currency": q.currency,
        "chg_1d": q.chg_1d, "chg_1w": q.chg_1w, "chg_1m": q.chg_1m,
        "rsi_14": q.rsi_14, "ma20_pct": q.ma20_pct, "vol_ratio": q.vol_ratio,
        "pe_trailing": q.pe_trailing, "pb": q.pb, "market_cap_b": q.market_cap_b,
        "score": q.score, "signal": q.signal, "error": q.error,
    }
