import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

class EquitySleeveEngine:
    """
    [Equity Portfolio Manager - Multi-Horizon & Systemic Risk Aware]
    Ledoit-Wolf Shrinkage와 Eigenvalue Concentration 진단을 통해 
    공분산 추정 오류와 시스템 리스크(Systemic Shock)를 방어하는 최고급 주식 슬리브 매니저입니다.
    """
    
    def __init__(self, turnover_lambda: float = 0.05) -> None:
        self.style_tickers = {
            "growth": "QQQ",    
            "value": "VTV",     
            "quality": "QUAL",  
            "size": "IWM"       
        }
        self.turnover_lambda = turnover_lambda

    def _erc_objective(self, weights: np.ndarray, cov_matrix: np.ndarray, 
                       target_risk_budgets: np.ndarray, 
                       prev_weights: Optional[np.ndarray]) -> float:
        """[목적 함수] ERC 오차 최소화 + Turnover 페널티"""
        port_var = weights.T @ cov_matrix @ weights
        if port_var <= 0: return 1e9
            
        mrc = cov_matrix @ weights
        rc_pct = (weights * mrc) / port_var
        
        error = np.sum(np.square(rc_pct - target_risk_budgets))
        if prev_weights is not None:
            turnover = np.sum(np.abs(weights - prev_weights))
            error += self.turnover_lambda * turnover
            
        return error

    def _get_multi_horizon_momentum(self, series: pd.Series) -> float:
        """
        [1순위 개선] Multi-Horizon Momentum
        1M(21일), 3M(63일), 6M(126일) 추세를 앙상블하여 단기 노이즈를 억제합니다.
        """
        if len(series) < 126: return 0.0
        
        mom_1m = (series.iloc[-1] / series.iloc[-21]) - 1.0
        mom_3m = (series.iloc[-1] / series.iloc[-63]) - 1.0
        mom_6m = (series.iloc[-1] / series.iloc[-126]) - 1.0
        
        return (0.3 * mom_1m) + (0.4 * mom_3m) + (0.3 * mom_6m)

    def optimize_sleeve(self, 
                        macro_states: Dict[str, float], 
                        price_df: pd.DataFrame, 
                        equity_budget: float,
                        prev_allocations: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        
        styles = list(self.style_tickers.keys())
        tickers = list(self.style_tickers.values())
        n = len(styles)

        if equity_budget <= 0.0:
            return {ticker: 0.0 for ticker in tickers}

        # 🌟 Step 1: Breadth Filter
        breadth_trend = 0.0
        if "Close_RSP" in price_df.columns and "Close_SPY" in price_df.columns:
            rsp, spy = price_df["Close_RSP"], price_df["Close_SPY"]
            breadth_ratio = rsp / spy
            if len(breadth_ratio) >= 20:
                breadth_trend = (breadth_ratio.iloc[-1] / breadth_ratio.iloc[-20]) - 1.0

        # 🌟 Step 2: Macro-to-Style Mapping
        g = macro_states.get("macro_growth", 0.0)
        i = macro_states.get("macro_inflation", 0.0)
        l = macro_states.get("macro_liquidity", 0.0)
        s = macro_states.get("macro_stress", 0.0)

        base_w = 0.25
        macro_scores = {
            "growth": base_w + (g * 0.15) + (l * 0.10) - (i * 0.05) - (max(0, s) * 0.20),
            "value": base_w + (i * 0.20) + (g * 0.05) - (l * 0.05),
            "quality": base_w + (max(0, s) * 0.15) + (l * 0.05),
            "size": base_w + (l * 0.20) + (g * 0.10) - (max(0, s) * 0.25)
        }

        # 🌟 Step 3: Returns & Multi-Horizon Momentum 계산
        returns = {}
        mom_scores = {}
        
        for style, ticker in self.style_tickers.items():
            if f"Close_{ticker}" in price_df.columns:
                series = price_df[f"Close_{ticker}"]
                daily_ret = series.pct_change().tail(60).fillna(0)
                
                returns[style] = daily_ret
                mom_scores[style] = self._get_multi_horizon_momentum(series)
            else:
                returns[style] = pd.Series(np.zeros(60))
                mom_scores[style] = 0.0

        ret_df = pd.DataFrame(returns)
        
        # 🌟 [2순위 개선] Covariance Shrinkage (Ledoit-Wolf)
        # 단순 Cov 계산 시 발생하는 노이즈와 역행렬 폭발을 방지
        try:
            lw = LedoitWolf()
            lw.fit(ret_df.values)
            cov_matrix = lw.covariance_ * 252
        except:
            # 예외 발생 시 단순 Cov로 Fallback
            cov_matrix = ret_df.cov().values * 252

        # 🌟 [3순위 개선] Eigenvalue Systemic Risk Filter
        # 공분산 행렬의 첫 번째 고유값(First Eigenvalue)이 전체에서 차지하는 비율 측정
        try:
            eigvals = np.linalg.eigvals(ret_df.corr().values)
            systemic_ratio = max(eigvals) / np.sum(eigvals) if np.sum(eigvals) > 0 else 0.25
        except:
            systemic_ratio = 0.25

        mom_values = list(mom_scores.values())
        mom_mean, mom_std = np.mean(mom_values), np.std(mom_values) + 1e-6
        
        raw_budgets = []
        for style in styles:
            z_mom = (mom_scores[style] - mom_mean) / mom_std
            combined_score = macro_scores[style] + (z_mom * 0.10)
            
            # Breadth 페널티
            if breadth_trend < -0.02: 
                if style == "size": combined_score -= 0.15
                elif style == "quality": combined_score += 0.10
                
            raw_budgets.append(max(0.01, combined_score)) 
            
        raw_budgets = np.array(raw_budgets)

        # [Systemic Shock 대응]: 1st 고유값이 70%를 넘어가면(시장이 1개의 팩터로 동기화 됨)
        # 위험(Active Bet)을 죽이고 1/N 평탄화 적용
        if systemic_ratio > 0.70:
            flat_budget = np.ones(n) * np.mean(raw_budgets)
            shrinkage = min(1.0, (systemic_ratio - 0.70) * 3.0) 
            raw_budgets = raw_budgets * (1 - shrinkage) + flat_budget * shrinkage

        target_risk_budgets = raw_budgets / np.sum(raw_budgets)

        # 🌟 Step 4: Turnover 페널티 전처리
        prev_weights = None
        if prev_allocations is not None:
            prev_w_list = [prev_allocations.get(ticker, 0.0) for ticker in tickers]
            prev_sum = sum(prev_w_list)
            if prev_sum > 0:
                prev_weights = np.array(prev_w_list) / prev_sum

        # 🌟 Step 5: Active ERC Optimization (Scipy SLSQP)
        init_weights = prev_weights if prev_weights is not None else np.ones(n) / n
        bounds = tuple((0.0, 1.0) for _ in range(n))
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0})

        if np.all(cov_matrix == 0):
            opt_weights = target_risk_budgets
        else:
            try:
                res = minimize(self._erc_objective, init_weights, 
                               args=(cov_matrix, target_risk_budgets, prev_weights),
                               method='SLSQP', bounds=bounds, constraints=constraints)
                opt_weights = res.x if res.success else target_risk_budgets
            except:
                opt_weights = target_risk_budgets

        # 🌟 Step 6: Final Capital Allocation Mapping
        final_allocations = {}
        for idx, ticker in enumerate(tickers):
            final_allocations[ticker] = round(float(opt_weights[idx]) * equity_budget, 4)

        return final_allocations