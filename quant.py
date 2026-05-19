import os
import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import yfinance as yf  # 🌟 FDR 대체
import statsmodels.api as sm
from sklearn.linear_model import Ridge
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import rankdata

# ==========================================
# 0. Environment & Logging
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

# ==========================================
# 1. Macro-to-Ontology Vector Target (어댑터 고도화)
# ==========================================
class MacroTaxonomyAdapter:
    def __init__(self):
        self.base_vector = {f"hybrid_{k}": 0.0 for k in [
            "growth", "value", "quality", "momentum", "size", "low_vol", "dividend", 
            "duration", "inflation", "real_rate", "usd", "commodity", "gold", "oil", 
            "kr_equity", "us_equity"
        ]}

    def translate(self, macro_asset_name: str) -> dict:
        t = self.base_vector.copy()
        macro = macro_asset_name.lower()
        
        # Region 추가로 1차 필터링 좁힘
        if macro == "us_growth":
            t.update({"hybrid_us_equity": 1.0, "hybrid_growth": 0.9, "hybrid_momentum": 0.6, "hybrid_usd": 1.0})
            return {"asset_class": "equity", "region": "US", "target_vector": t}
        elif macro == "us_value":
            t.update({"hybrid_us_equity": 1.0, "hybrid_value": 0.9, "hybrid_usd": 1.0})
            return {"asset_class": "equity", "region": "US", "target_vector": t}
        elif macro == "us_dividend":
            t.update({"hybrid_us_equity": 1.0, "hybrid_dividend": 1.0, "hybrid_value": 0.5, "hybrid_usd": 1.0})
            return {"asset_class": "equity", "region": "US", "target_vector": t}
        elif macro == "kr_equity":
            t.update({"hybrid_kr_equity": 1.0})
            return {"asset_class": "equity", "region": "KR", "target_vector": t}
        elif macro == "long_bond":
            t.update({"hybrid_duration": 1.0, "hybrid_real_rate": -0.8})
            return {"asset_class": "bond", "region": "US", "target_vector": t}
        else:
            return None

# ==========================================
# 2. Institutional Quant Optimizer Engine (V16)
# ==========================================
class InstitutionalQuantEngine:
    def __init__(self, db_path: str = "data/registry/master_etf.db", struct_weight: float = 0.4):
        self.db_path = db_path
        self.w_struct = struct_weight
        self.w_stat = 1.0 - struct_weight
        self.adapter = MacroTaxonomyAdapter()

    def get_tradable_universe(self, account_type: str = "NORMAL") -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT 
                s.ticker, s.name, s.asset_class, s.region, s.tax_treatment, e.execution_score_log,
                v.growth as st_growth, v.value as st_value, v.dividend as st_div, v.duration as st_dur,
                v.kr_equity as st_kor, v.us_equity as st_us, v.usd as st_usd, v.gold as st_gold,
                v.quality, v.momentum, v.size, v.low_vol, v.inflation, v.real_rate, v.commodity, v.oil,
                stat.beta_growth as dyn_growth, stat.beta_value as dyn_value, stat.beta_div as dyn_div, 
                stat.beta_dur as dyn_dur, stat.beta_kor as dyn_kor, stat.beta_mkt as dyn_us, 
                stat.beta_usd as dyn_usd, stat.beta_gold as dyn_gold, stat.r_squared
            FROM etf_structural s
            JOIN etf_exposure_vector v ON s.ticker = v.ticker
            JOIN etf_statistical_vector stat ON s.ticker = stat.ticker
            JOIN etf_execution_profile e ON s.ticker = e.ticker
            WHERE e.execution_score_log > 0
        """
        if account_type == "PENSION": query += " AND s.pension_eligible = 1"
        df = pd.read_sql(query, conn)
        conn.close()
        if df.empty: return df

        # 단위계 통일: Beta 값을 np.tanh()로 압축 정규화 (-1.0 ~ 1.0)
        stat_cols = ['dyn_growth', 'dyn_value', 'dyn_div', 'dyn_dur', 'dyn_kor', 'dyn_us', 'dyn_usd', 'dyn_gold']
        for col in stat_cols:
            df[col] = np.tanh(df[col] * 1.5)

        has_stat = df['r_squared'] > 0
        w_st = np.where(has_stat, self.w_struct, 1.0)
        w_dy = np.where(has_stat, self.w_stat, 0.0)

        # 하이브리드 벡터 병합
        df['hybrid_growth'] = (df['st_growth'] * w_st) + (df['dyn_growth'] * w_dy)
        df['hybrid_value'] = (df['st_value'] * w_st) + (df['dyn_value'] * w_dy)
        df['hybrid_dividend'] = (df['st_div'] * w_st) + (df['dyn_div'] * w_dy)
        df['hybrid_duration'] = (df['st_dur'] * w_st) + (df['dyn_dur'] * w_dy)
        df['hybrid_kr_equity'] = (df['st_kor'] * w_st) + (df['dyn_kor'] * w_dy)
        df['hybrid_us_equity'] = (df['st_us'] * w_st) + (df['dyn_us'] * w_dy)
        df['hybrid_usd'] = (df['st_usd'] * w_st) + (df['dyn_usd'] * w_dy)
        df['hybrid_gold'] = (df['st_gold'] * w_st) + (df['dyn_gold'] * w_dy)
        
        # 회귀 프록시 없는 차원 보존
        df['hybrid_size'] = df['size']
        df['hybrid_quality'] = df['quality']
        df['hybrid_momentum'] = df['momentum']
        df['hybrid_low_vol'] = df['low_vol']
        df['hybrid_inflation'] = df['inflation']
        df['hybrid_real_rate'] = df['real_rate']
        df['hybrid_commodity'] = df['commodity']
        df['hybrid_oil'] = df['oil']
        
        # 유동성 백분위수 (0~1.0)
        df['liq_percentile'] = rankdata(df['execution_score_log']) / len(df)
        return df

    def _load_benchmarks(self) -> pd.DataFrame:
        logging.info("🌐 [yfinance] 9-Factor Benchmark Matrix 주간 데이터 로드 중...")
        # 🌟 yfinance용 벤치마크 심볼 (원달러 환율 KRW=X 반영)
        self.benchmarks = {
            "MKT": "SPY", "GROWTH": "QQQ", "VALUE": "VTV", "DIV": "SCHD", 
            "SIZE": "IWM", "DUR": "TLT", "GOLD": "GLD", "KOR": "EWY", "USD": "KRW=X"
        }
        end_date = datetime.today()
        start_date = end_date - timedelta(days=365)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        df_list = []
        for name, ticker in self.benchmarks.items():
            try:
                # 🌟 yf.Ticker().history() 방식으로 안정적인 단일 종목 데이터 추출
                hist = yf.Ticker(ticker).history(start=start_str, end=end_str)
                if not hist.empty and 'Close' in hist.columns:
                    df = hist[['Close']].rename(columns={'Close': name})
                    df_weekly = df.resample('W-FRI').last()
                    df_list.append(df_weekly.pct_change(fill_method=None).dropna()) 
            except Exception as e:
                logging.error(f"벤치마크 {name}({ticker}) 로드 실패: {e}")
                
        if not df_list: raise ValueError("벤치마크 데이터를 하나도 불러오지 못했습니다.")
        return pd.concat(df_list, axis=1).dropna()

    def calculate_ridge_betas(self, ticker: str) -> dict:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=365)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        default_betas = {k: 0.0 for k in self.benchmarks.keys()}
        default_betas["R2"] = 0.0
        
        try:
            # 🌟 한국 ETF 조회를 위해 yfinance 표준인 .KS 접미사 사용
            symbol = f"{ticker}.KS"
            hist = yf.Ticker(symbol).history(start=start_str, end=end_str)
            
            # 실패 시 접미사 없이 재시도 (미국 ETF 등의 경우 대비)
            if hist.empty: 
                hist = yf.Ticker(ticker).history(start=start_str, end=end_str)
                
            if hist.empty or 'Close' not in hist.columns: 
                return default_betas
            
            etf_weekly = hist[['Close']].resample('W-FRI').last()
            etf_returns = etf_weekly.pct_change(fill_method=None).dropna().rename(columns={'Close': 'ETF'})
            
            merged = pd.concat([etf_returns, self.benchmark_returns], axis=1).dropna()
            if len(merged) < 20: return default_betas 
                
            y = merged['ETF']
            X = merged[list(self.benchmarks.keys())]
            
            ridge = Ridge(alpha=0.5, fit_intercept=True)
            ridge.fit(X, y)
            
            result = {factor: round(coef, 3) for factor, coef in zip(X.columns, ridge.coef_)}
            result["R2"] = round(ridge.score(X, y), 3) 
            return result
            
        except Exception:
            return default_betas

    def _calculate_exposure_distance(self, target_vector: dict, candidate_row: pd.Series) -> float:
        keys = list(target_vector.keys())
        t_arr = np.array([target_vector[k] for k in keys]).reshape(1, -1)
        c_arr = np.array([candidate_row[k] for k in keys]).reshape(1, -1)
        
        mag_t, mag_c = np.linalg.norm(t_arr), np.linalg.norm(c_arr)
        if mag_t == 0 or mag_c == 0: return 0.0
            
        cos_sim = cosine_similarity(t_arr, c_arr)[0][0]
        mag_score = min(mag_c / mag_t, 1.0)
        return (cos_sim * 0.7) + (mag_score * 0.3)

    def run_account_allocation(self, account_type: str, macro_weights: dict) -> pd.DataFrame:
        logging.info(f"🎯 [{account_type}] V16 Calibrated Optimizer 할당 시작 (yfinance Data Feed)")
        
        universe = self.get_tradable_universe(account_type=account_type)
        if universe.empty: return pd.DataFrame()
            
        allocations, selected_vectors = [], []

        for macro_asset, weight in macro_weights.items():
            translated = self.adapter.translate(macro_asset)
            if not translated: continue
            
            target_v = translated['target_vector']
            
            candidates = universe[
                (universe['asset_class'] == translated['asset_class']) & 
                (universe['region'] == translated['region'])
            ].copy()
            
            if candidates.empty: continue
            
            scores = []
            for _, row in candidates.iterrows():
                # 1. 융합된 Hybrid 벡터 거리
                sim_score = self._calculate_exposure_distance(target_vector=target_v, candidate_row=row)
                
                # 2. 유동성 및 세금
                liq_score = row['liq_percentile']
                tax_score = 1.0 if "tax_free" in row['tax_treatment'] else 0.8
                
                # 3. Threshold 기반 현실적인 Overlap Penalty (85% 이상만 강한 타격)
                overlap_penalty = 0.0
                if selected_vectors:
                    c_arr = np.array([row[k] for k in target_v.keys()]).reshape(1, -1)
                    centroid = np.mean(np.array(selected_vectors), axis=0).reshape(1, -1)
                    overlap = cosine_similarity(c_arr, centroid)[0][0]
                    overlap_penalty = max(0, overlap - 0.85) * 0.5 
                
                scores.append((sim_score * 0.5) + (liq_score * 0.3) + (tax_score * 0.2) - overlap_penalty)
                
            candidates['score'] = scores
            candidates = candidates.sort_values(by='score', ascending=False)
            best_etf = candidates.iloc[0]
            
            if best_etf['score'] <= 0: continue
            selected_vectors.append(np.array([best_etf[k] for k in target_v.keys()]).flatten())
            
            allocations.append({
                "Target": macro_asset.upper(), "Weight": f"{int(weight*100)}%",
                "Ticker": best_etf['ticker'], "Name": best_etf['name'],
                "Score": round(best_etf['score'], 3),
                "Hyb_Value": round(best_etf['hybrid_value'], 2),
                "Hyb_Growth": round(best_etf['hybrid_growth'], 2),
                "Hyb_Div": round(best_etf['hybrid_dividend'], 2)
            })
            
        return pd.DataFrame(allocations)

# ==========================================
# 3. 실전 시스템 통합 가동
# ==========================================
class AdvancedMacroEngine:
    def get_optimal_weights(self) -> dict:
        return {
            "us_value": 0.40,   
            "us_dividend": 0.30, 
            "us_growth": 0.30
        }

if __name__ == "__main__":
    print("\n" + "="*120)
    print(" 🧠 [ETF Operating System] V16. The Calibrated Optimizer (yfinance Data Feed)")
    print("="*120)
    
    macro_engine = AdvancedMacroEngine()
    live_weights = macro_engine.get_optimal_weights()
    logging.info(f"📊 [Macro Engine] 수신된 매크로 타겟 비중: {live_weights}")
    
    engine = InstitutionalQuantEngine(struct_weight=0.4) 
    pf = engine.run_account_allocation(account_type="NORMAL", macro_weights=live_weights)
    
    print("\n✅ 최종 라우팅 리포트 (yfinance 기반 스케일 정규화 및 Threshold 패널티 적용)")
    print("-" * 120)
    if not pf.empty: print(pf.to_string(index=False))
    print("\n" + "="*120 + "\n")