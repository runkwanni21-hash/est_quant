import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List

from data_engineering.repository.etf_repository import BaseETFRepository, MemoryETFRepository
from data_engineering.providers.base_provider import BaseETFProvider

class KoreaETFMapper:
    """추상 팩터 비중을 Exposure Vector 기반 한국 ETF 포트폴리오로 번역합니다."""
    
    def __init__(self, 
                 providers: Optional[List[BaseETFProvider]] = None,
                 repository: Optional[BaseETFRepository] = None) -> None:
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.providers = providers or []
        
        # 시스템 콜드 스타트(Cold Start) 시 기본 주입될 하드코딩 팩터 뼈대 (향후 Factor Engine에서 대체)
        initial_db = {
            
        }
        self.repository = repository or MemoryETFRepository(initial_data=initial_db)

    def update_metadata(self) -> None:
        """병렬 수집(IO-Bound)을 수행하고 Repository에 트랜잭션 단위로 일괄 반영합니다."""
        if not self.providers:
            return
            
        # 운용사 수가 늘어나더라도 Rate Limit/Contention 방어를 위해 max_workers 제한
        optimal_workers = min(8, len(self.providers))
        
        with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
            future_to_provider = {
                executor.submit(provider.fetch_metadata): provider 
                for provider in self.providers
            }
            
            for future in as_completed(future_to_provider):
                provider = future_to_provider[future]
                try:
                    fetched_etfs = future.result() 
                    # 원자성(Atomicity)이 보장된 Bulk Upsert 수행
                    self.repository.bulk_upsert(fetched_etfs)
                except Exception:
                    self.logger.exception(f"[{provider.name}] 파이프라인 동기화 실패 (DB Rollback 됨)")

    def _get_execution_quality(self, data: Dict[str, Any]) -> float:
        """유동성 점수와 보수를 결합하여 최종 실행 우선순위를 계산합니다."""
        return (data.get("liquidity_score", 0.0) * 2.0) - (data.get("fee", 0.0) * 1000)

    def _select_best_etf(self, target_factor: str, target_tier: str) -> Optional[str]:
        """추상 팩터(factor)에 가장 잘 부합하고 유동성이 좋은 1등 ETF를 탐색합니다."""
        # 공유 Dict 직접 접근이 아닌 Query Interface를 호출하여 원본 오염 완벽 차단
        candidates = self.repository.find_candidates(target_factor, target_tier)
        
        if not candidates: 
            return None
            
        scored = {t: self._get_execution_quality(d) for t, d in candidates.items()}
        return max(scored, key=scored.get)

    def translate_to_korea_portfolio(self, abstract_allocations: Dict[str, float], fx_hedge_ratio: float, market_stress: float) -> Dict[str, float]:
        """
        추상화된 글로벌 매크로 자산 비중을 실제 한국 시장 ETF 비중(%)으로 번역합니다.
        Core-Satellite 및 환헤지(H) / 환노출(UH) 동적 배분 적용.
        """
        portfolio: Dict[str, float] = {}
        
        for factor, budget in abstract_allocations.items():
            if budget <= 0.001: 
                continue
            
            # 현금성 자산, 원자재, 사이즈(중소형) 팩터는 대체/분할 없이 단일 종목 다이렉트 맵핑
            if factor in ["cash_target", "commodity", "size"]:
                ticker = self._select_best_etf(factor, "core") or self._select_best_etf(factor, "hedged")
                if ticker: 
                    portfolio[ticker] = portfolio.get(ticker, 0.0) + budget
                continue

            hedge_budget: float = budget * fx_hedge_ratio
            unhedged_budget: float = budget - hedge_budget

            # 1. 환헤지(H) 물량 배정
            if hedge_budget > 0:
                h_ticker = self._select_best_etf(factor, "hedged")
                if h_ticker: 
                    portfolio[h_ticker] = portfolio.get(h_ticker, 0.0) + hedge_budget
                else: 
                    unhedged_budget += hedge_budget # 헤지 종목이 없으면 노출형으로 이월

            # 2. 환노출(UH) Core-Satellite 물량 배정
            if unhedged_budget > 0:
                c_ticker = self._select_best_etf(factor, "core")
                s_ticker = self._select_best_etf(factor, "satellite")
                
                # 시장 스트레스(Fragility)가 높을수록 Satellite(레버리지/테마) 비중을 0에 가깝게 축소
                sat_ratio: float = max(0.0, 0.30 - (market_stress * 0.5)) if s_ticker else 0.0
                core_ratio: float = 1.0 - sat_ratio

                if c_ticker: 
                    portfolio[c_ticker] = portfolio.get(c_ticker, 0.0) + (unhedged_budget * core_ratio)
                if s_ticker and sat_ratio > 0: 
                    portfolio[s_ticker] = portfolio.get(s_ticker, 0.0) + (unhedged_budget * sat_ratio)

        # 3. 비중 최종 정규화 (100% 맞춤)
        total: float = sum(portfolio.values())
        if total > 0: 
            portfolio = {k: round(v / total, 4) for k, v in portfolio.items()}
            
        return portfolio