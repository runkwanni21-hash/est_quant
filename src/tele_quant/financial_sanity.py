"""Financial metric sanity checker — 재무 데이터 이상치 감지.

yfinance/DART에서 가져온 재무 지표가 현실적 범위를 벗어나면
경고 플래그를 반환한다. 데이터를 지어내거나 보정하지 않고
"확인 제한" 또는 "주의" 메시지를 출력용으로만 제공한다.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SanityFlag:
    field: str
    value: float | None
    message: str
    severity: str  # "WARN" | "INFO"


@dataclass
class SanityResult:
    flags: list[SanityFlag] = field(default_factory=list)
    confidence: str = "HIGH"   # HIGH | MEDIUM | LOW
    note: str = ""

    def add(self, field: str, value: float | None, msg: str, severity: str = "WARN") -> None:
        self.flags.append(SanityFlag(field=field, value=value, message=msg, severity=severity))
        if severity == "WARN" and self.confidence == "HIGH":
            self.confidence = "MEDIUM"

    @property
    def warn_lines(self) -> list[str]:
        return [f"주의: {f.message}" for f in self.flags if f.severity == "WARN"]

    @property
    def info_lines(self) -> list[str]:
        return [f"참고: {f.message}" for f in self.flags if f.severity == "INFO"]

    def summary_line(self) -> str:
        """단일 요약 줄 — 브리핑 출력용."""
        if not self.flags:
            return ""
        return " | ".join(f.message for f in self.flags if f.severity == "WARN")[:160]


# ── 섹터별 허용 범위 ─────────────────────────────────────────────────────────

_SECTOR_PE_RANGES: dict[str, tuple[float, float]] = {
    # (min_reasonable, max_reasonable_warn)
    "default":            (-500.0, 200.0),
    "bio":                (-9999.0, 9999.0),   # 바이오는 PER 무의미 (적자 다수)
    "saas":               (-50.0, 500.0),       # 고PER 허용
    "semiconductor":      (-50.0, 300.0),
    "financial":          (-20.0, 30.0),
    "utility":            (-10.0, 30.0),
    "commodity":          (-100.0, 100.0),
}

_SECTOR_ROE_WARN: dict[str, float] = {
    "default":       100.0,
    "financial":     40.0,
    "saas":          200.0,   # SaaS buyback → negative equity 가능
    "consumer":      80.0,
}

_SECTOR_DIV_WARN: dict[str, float] = {
    "default":    20.0,
    "reit":       15.0,       # 리츠는 높은 배당 정상
    "utility":    12.0,
}


def _sector_id(sector: str) -> str:
    s = sector.lower()
    if any(k in s for k in ("bio", "pharma", "health", "clinical", "biopharma")):
        return "bio"
    if any(k in s for k in ("software", "saas", "cloud", "internet", "tech services")):
        return "saas"
    if any(k in s for k in ("semiconductor", "electronic", "chip")):
        return "semiconductor"
    if any(k in s for k in ("bank", "financ", "insur", "capital")):
        return "financial"
    if any(k in s for k in ("utility", "electric", "gas utility")):
        return "utility"
    if any(k in s for k in ("energy", "oil", "mining", "material", "chemical")):
        return "commodity"
    if any(k in s for k in ("real estate", "reit")):
        return "reit"
    if any(k in s for k in ("consumer", "retail", "food")):
        return "consumer"
    return "default"


def check_financial_sanity(
    *,
    pe_trailing: float | None = None,
    pe_forward: float | None = None,
    pb: float | None = None,
    roe: float | None = None,                # % (e.g., 15.0 = 15%)
    eps_growth: float | None = None,         # % (e.g., 50.0 = 50%)
    revenue_growth: float | None = None,     # %
    dividend_yield: float | None = None,     # % (e.g., 3.5 = 3.5%)
    op_margin: float | None = None,          # %
    debt_to_equity: float | None = None,
    current_price: float | None = None,
    market: str = "US",
    sector: str = "",
) -> SanityResult:
    """재무 지표 이상치 탐지.

    Returns:
        SanityResult with flags and confidence level.
    """
    result = SanityResult()
    sid = _sector_id(sector)

    # ── 배당수익률 ────────────────────────────────────────────────────────────
    if dividend_yield is not None:
        warn_threshold = _SECTOR_DIV_WARN.get(sid, _SECTOR_DIV_WARN["default"])
        if dividend_yield > warn_threshold:
            result.add(
                "dividend_yield", dividend_yield,
                f"배당수익률 {dividend_yield:.1f}% — 데이터 확인 필요 (yfinance 오류 가능성)",
            )
        elif dividend_yield > 50.0:
            result.add(
                "dividend_yield", dividend_yield,
                f"배당수익률 {dividend_yield:.1f}% — 심각한 데이터 오류 의심",
            )

    # ── ROE ───────────────────────────────────────────────────────────────────
    if roe is not None:
        warn_threshold = _SECTOR_ROE_WARN.get(sid, _SECTOR_ROE_WARN["default"])
        if roe > warn_threshold:
            result.add(
                "roe", roe,
                f"ROE {roe:.0f}% — 일회성/자본잠식/데이터 확인 필요",
            )
        elif roe < -200.0:
            result.add(
                "roe", roe,
                f"ROE {roe:.0f}% 심각한 적자 — 자본잠식 또는 데이터 오류 확인 필요",
            )

    # ── EPS 성장률 ───────────────────────────────────────────────────────────
    if eps_growth is not None:
        if eps_growth > 300.0:
            result.add(
                "eps_growth", eps_growth,
                f"EPS성장률 {eps_growth:.0f}% — 기저효과 가능성 또는 데이터 확인 필요",
            )
        elif eps_growth < -90.0:
            result.add(
                "eps_growth", eps_growth,
                f"EPS성장률 {eps_growth:.0f}% — 대규모 손실 또는 비교기간 이슈",
                severity="INFO",
            )

    # ── PBR ──────────────────────────────────────────────────────────────────
    if pb is not None and sid not in ("saas", "bio"):
        if pb > 50.0:
            result.add(
                "pb", pb,
                f"PBR {pb:.1f}배 — SaaS/고ROE 특수 섹터 아니면 데이터 확인 필요",
            )
        elif pb < 0:
            result.add(
                "pb", pb,
                f"PBR {pb:.1f}배 음수 — 자본잠식 가능성",
                severity="INFO",
            )

    # ── PER ──────────────────────────────────────────────────────────────────
    if pe_trailing is not None and sid not in ("bio",):
        pe_range = _SECTOR_PE_RANGES.get(sid, _SECTOR_PE_RANGES["default"])
        if pe_trailing > pe_range[1]:
            result.add(
                "pe_trailing", pe_trailing,
                f"PER {pe_trailing:.0f}배 — 섹터 기준 초과, 이익 급감 또는 데이터 확인",
                severity="INFO",
            )

    # ── 영업이익률 ───────────────────────────────────────────────────────────
    if op_margin is not None:
        if op_margin > 80.0:
            result.add(
                "op_margin", op_margin,
                f"영업이익률 {op_margin:.0f}% — 데이터 확인 필요 (일회성 가능성)",
                severity="INFO",
            )
        elif op_margin < -100.0:
            result.add(
                "op_margin", op_margin,
                f"영업이익률 {op_margin:.0f}% — 고정비 초과 대규모 손실",
                severity="INFO",
            )

    # ── KR 현재가 스케일 이상 탐지 ──────────────────────────────────────────
    if market == "KR" and current_price is not None:
        if current_price > 1_500_000:
            result.add(
                "current_price", current_price,
                f"현재가 {current_price:,.0f}원 — 비정상적 스케일, yfinance 데이터 확인 필요",
            )
        elif current_price <= 0:
            result.add(
                "current_price", current_price,
                "현재가 0 이하 — 데이터 오류",
            )

    # ── 신뢰도 최종 설정 ────────────────────────────────────────────────────
    warn_count = sum(1 for f in result.flags if f.severity == "WARN")
    if warn_count >= 3:
        result.confidence = "LOW"
    elif warn_count >= 1:
        result.confidence = "MEDIUM"

    return result


def format_sanity_note(result: SanityResult) -> str:
    """출력용 단일 줄 또는 빈 문자열."""
    if not result.flags:
        return ""
    warns = result.warn_lines
    if not warns:
        return ""
    conf_label = f"재무 데이터 신뢰도: {result.confidence}"
    return conf_label + " | " + " | ".join(warns[:3])


# ── KR ticker canonicalization ───────────────────────────────────────────────

_KQ_CODES: frozenset[str] = frozenset()   # lazy-loaded from ticker_aliases.yml


def _load_kq_codes() -> frozenset[str]:
    """KOSDAQ 6자리 코드 집합 (lazy)."""
    global _KQ_CODES
    if _KQ_CODES:
        return _KQ_CODES
    try:
        from pathlib import Path

        import yaml

        cfg_path = Path(__file__).parent.parent.parent / "config" / "ticker_aliases.yml"
        if not cfg_path.exists():
            return frozenset()
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        codes: set[str] = set()
        for sym, info in data.items():
            if isinstance(info, dict) and info.get("market", "").upper() == "KQ":
                bare = sym.replace(".KQ", "").replace(".KS", "")
                if bare.isdigit():
                    codes.add(bare.zfill(6))
        _KQ_CODES = frozenset(codes)
    except Exception:
        pass
    return _KQ_CODES


def canonicalize_kr_ticker(raw: str) -> str:
    """KR 티커를 6자리.KS/.KQ 형식으로 정규화.

    Args:
        raw: 17856 / 432 / 005930 / 005930.KS / NVDA 등

    Returns:
        005930.KS 형식 또는 원본(비 KR).
    """
    s = raw.strip().upper()

    # 이미 완전한 형식
    if s.endswith(".KS") or s.endswith(".KQ"):
        parts = s.rsplit(".", 1)
        code = parts[0].zfill(6)
        return f"{code}.{parts[1]}"

    # 순수 숫자
    if s.isdigit():
        code = s.zfill(6)
        kq_codes = _load_kq_codes()
        if code in kq_codes:
            return f"{code}.KQ"
        return f"{code}.KS"

    return raw


def is_bare_kr_ticker(s: str) -> bool:
    """1~5자리 숫자이면 zero-padding이 깨진 KR 티커로 판단."""
    return s.isdigit() and 1 <= len(s) <= 5
