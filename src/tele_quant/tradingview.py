"""TradingView 차트 링크 생성기.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

__all__ = ["chart_url"]

_INTERVAL_MAP: dict[str, str] = {
    "4H": "240",
    "4h": "240",
    "1D": "D",
    "1d": "D",
    "1W": "W",
    "1w": "W",
    "240": "240",
    "D": "D",
    "W": "W",
}


def chart_url(symbol: str, market: str = "", interval: str = "240") -> str:
    """TradingView 차트 직접 링크 반환.

    Args:
        symbol:   종목 코드 (예: 005930.KS, 000660.KQ, NVDA)
        market:   KR | US (빈 문자열이면 symbol 접미사로 자동 판별)
        interval: TV 인터벌 — "4H"|"240"(4시간), "1D"|"D"(일봉), "1W"|"W"(주봉)

    Returns:
        https://www.tradingview.com/chart/?symbol=<EXCHANGE>:<CODE>&interval=<INTERVAL>
    """
    tv_interval = _INTERVAL_MAP.get(interval, interval)
    is_kr = market == "KR" or symbol.endswith((".KS", ".KQ"))

    if is_kr:
        code = symbol.split(".")[0]
        exchange = "KOSDAQ" if symbol.endswith(".KQ") else "KRX"
        tv_symbol = f"{exchange}:{code}"
    else:
        tv_symbol = symbol.split(".")[0].upper()

    return f"https://www.tradingview.com/chart/?symbol={tv_symbol}&interval={tv_interval}"
