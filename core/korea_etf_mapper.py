import pandas as pd
from typing import Dict, Any, Optional

class KoreaETFMapper:
    """추상 팩터 비중을 Exposure Vector 기반 Core-Satellite 한국 ETF 포트폴리오로 번역합니다."""
    def __init__(self):
        self.etf_db = {
            "133690": {"name": "TIGER 미국나스닥100", "tier": "core", "fx": "UH", "vector": {"growth": 0.9}, "liquidity_score": 9.5, "fee": 0.0007},
            "449780": {"name": "KODEX 미국테크TOP10", "tier": "satellite", "fx": "UH", "vector": {"growth": 1.2}, "liquidity_score": 8.0, "fee": 0.0045},
            "304940": {"name": "KODEX 미국나스닥100(H)", "tier": "hedged", "fx": "H", "vector": {"growth": 0.9}, "liquidity_score": 7.5, "fee": 0.0045},
            
            "360750": {"name": "TIGER 미국S&P500", "tier": "core", "fx": "UH", "vector": {"value": 0.8, "quality": 0.8}, "liquidity_score": 9.8, "fee": 0.0007},
            "314250": {"name": "KODEX 미국S&P500(H)", "tier": "hedged", "fx": "H", "vector": {"value": 0.8, "quality": 0.8}, "liquidity_score": 6.0, "fee": 0.0045},
            
            "280930": {"name": "KODEX 미국러셀2000(H)", "tier": "hedged", "fx": "H", "vector": {"size": 1.0}, "liquidity_score": 7.0, "fee": 0.0045},
            
            "466950": {"name": "ACE 미국배당다우존스", "tier": "core", "fx": "UH", "vector": {"income": 0.9}, "liquidity_score": 9.0, "fee": 0.0001},
            
            "308620": {"name": "KODEX 미국채10년선물", "tier": "core", "fx": "UH", "vector": {"bond": 1.0}, "liquidity_score": 7.0, "fee": 0.0030},
            "461580": {"name": "ACE 미국30년국채액티브(H)", "tier": "hedged", "fx": "H", "vector": {"bond": 1.5}, "liquidity_score": 8.5, "fee": 0.0005},
            
            "411060": {"name": "KODEX 골드선물(H)", "tier": "hedged", "fx": "H", "vector": {"commodity": 1.0}, "liquidity_score": 6.5, "fee": 0.0068},
            "357870": {"name": "TIGER CD금리투자KIS(합성)", "tier": "core", "fx": "UH", "vector": {"cash_target": 1.0}, "liquidity_score": 10.0, "fee": 0.0003},
        }

    def _get_execution_quality(self, data: Dict[str, Any]) -> float:
        return (data["liquidity_score"] * 2.0) - (data["fee"] * 1000)

    def _select_best_etf(self, target_factor: str, target_tier: str) -> Optional[str]:
        candidates = {t: d for t, d in self.etf_db.items() if d["tier"] == target_tier and target_factor in d["vector"]}
        if not candidates: return None
        scored = {t: self._get_execution_quality(d) for t, d in candidates.items()}
        return max(scored, key=scored.get)

    def translate_to_korea_portfolio(self, abstract_allocations: Dict[str, float], fx_hedge_ratio: float, market_stress: float) -> Dict[str, float]:
        portfolio = {}
        for factor, budget in abstract_allocations.items():
            if budget <= 0.001: continue
            
            # 현금 및 대체불가 팩터 다이렉트 맵핑
            if factor in ["cash_target", "commodity", "size"]:
                ticker = self._select_best_etf(factor, "core") or self._select_best_etf(factor, "hedged")
                if ticker: portfolio[ticker] = portfolio.get(ticker, 0.0) + budget
                continue

            hedge_budget = budget * fx_hedge_ratio
            unhedged_budget = budget - hedge_budget

            if hedge_budget > 0:
                h_ticker = self._select_best_etf(factor, "hedged")
                if h_ticker: portfolio[h_ticker] = portfolio.get(h_ticker, 0.0) + hedge_budget
                else: unhedged_budget += hedge_budget

            if unhedged_budget > 0:
                c_ticker, s_ticker = self._select_best_etf(factor, "core"), self._select_best_etf(factor, "satellite")
                sat_ratio = max(0.0, 0.30 - (market_stress * 0.5)) if s_ticker else 0.0
                core_ratio = 1.0 - sat_ratio

                if c_ticker: portfolio[c_ticker] = portfolio.get(c_ticker, 0.0) + (unhedged_budget * core_ratio)
                if s_ticker and sat_ratio > 0: portfolio[s_ticker] = portfolio.get(s_ticker, 0.0) + (unhedged_budget * sat_ratio)

        total = sum(portfolio.values())
        if total > 0: portfolio = {k: round(v / total, 4) for k, v in portfolio.items()}
        return portfolio