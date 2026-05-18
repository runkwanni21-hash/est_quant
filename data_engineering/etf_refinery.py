import os
import re
import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from sklearn.linear_model import Ridge

# ==========================================
# 0. Environment & Logging
# ==========================================
def setup_environment():
    folders = ['data/raw', 'data/processed', 'data/cache', 'data/registry']
    for f in folders: os.makedirs(f, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ==========================================
# 1. Rules & Tax
# ==========================================
class StructuralRules:
    def __init__(self):
        self.bond = re.compile(r"국채|국고채|회사채|종합채권|채권|KOFR|CD금리|SOFR")
        self.commodity = re.compile(r"골드|금|원유|WTI")
        self.region_kr = re.compile(r"KODEX 200|TIGER 200|국고채|KOFR|CD금리|레버리지")
        self.region_us = re.compile(r"미국|나스닥|S&P|다우존스|US")
        
    def classify_asset(self, name: str) -> str:
        if "KOFR" in name or "CD금리" in name: return "cash"
        if self.bond.search(name): return "bond"
        if self.commodity.search(name): return "commodity"
        return "equity"

class ExposureRules:
    def generate_base_vector(self, name: str, asset_class: str) -> dict:
        v = {k: 0.0 for k in ["growth", "value", "quality", "momentum", "size", "low_vol", "dividend", "duration", "inflation", "real_rate", "usd", "commodity", "gold", "oil", "kr_equity", "us_equity"]}
        if asset_class == "equity":
            if "미국" in name: v["us_equity"] = 1.0
            if "200" in name: v["kr_equity"] = 1.0
            if "나스닥" in name or "테크" in name: v["growth"] = 0.9; v["momentum"] = 0.7
            if "가치" in name or "다우존스" in name: v["value"] = 0.8
            if "배당" in name: v["dividend"] = 0.9; v["quality"] = 0.6
        if asset_class == "bond":
            if "30년" in name: v["duration"] = 1.0; v["real_rate"] = -0.9
            elif "10년" in name: v["duration"] = 0.6; v["real_rate"] = -0.5
            elif "3년" in name: v["duration"] = 0.2; v["real_rate"] = -0.2
        if asset_class == "commodity":
            v["commodity"] = 1.0
            if "골드" in name: v["gold"] = 1.0; v["inflation"] = 0.5
            if "원유" in name: v["oil"] = 1.0; v["inflation"] = 0.9
        return v

# ==========================================
# 2. Providers & Data Source
# ==========================================
class UnifiedProvider:
    def fetch_universe(self):
        return {
            "449780": "KODEX 미국테크TOP10", "304940": "KODEX 미국나스닥100선물(H)", 
            "314250": "KODEX 미국S&P500선물(H)", "308620": "KODEX 미국채10년선물",
            "411060": "KODEX 골드선물(H)", "114260": "KODEX 국고채3년", 
            "449170": "KODEX KOFR금리액티브(합성)", "069500": "KODEX 200", 
            "122630": "KODEX 레버리지", "133690": "TIGER 미국나스닥100", 
            "360750": "TIGER 미국S&P500", "382490": "TIGER 미국가치주", 
            "418120": "TIGER 미국배당+7%프리미엄다우존스", "329200": "TIGER 미국배당성장", 
            "305080": "TIGER 미국채10년선물", "130680": "TIGER 원유선물Enhanced(H)", 
            "357870": "TIGER CD금리투자KIS(합성)", "102110": "TIGER 200",
            "466920": "ACE 미국빅테크TOP7", "466950": "ACE 미국배당다우존스", 
            "461580": "ACE 미국30년국채액티브(H)"
        }

class StatisticalEngine:
    """9-Factor Benchmark를 바탕으로 52주 Rolling Regression을 수행하는 엔진"""
    def __init__(self):
        self.benchmarks = {
            "beta_mkt": "SPY", "beta_growth": "QQQ", "beta_value": "VTV", 
            "beta_div": "SCHD", "beta_size": "IWM", "beta_dur": "TLT", 
            "beta_gold": "GLD", "beta_kor": "EWY", "beta_usd": "USD/KRW"
        }
        self.start_str = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        self.end_str = datetime.today().strftime("%Y-%m-%d")
        self.bench_df = self._load_benchmarks()

    def _load_benchmarks(self):
        df_list = []
        for name, ticker in self.benchmarks.items():
            df = fdr.DataReader(ticker, self.start_str, self.end_str)
            if not df.empty:
                df = df[['Close']].rename(columns={'Close': name}).resample('W-FRI').last()
                df_list.append(df.pct_change(fill_method=None).dropna())
        return pd.concat(df_list, axis=1).dropna() if df_list else pd.DataFrame()

    def calculate_stat_vector(self, ticker: str) -> dict:
        default_res = {k: 0.0 for k in self.benchmarks.keys()}
        default_res["r_squared"] = 0.0
        if self.bench_df.empty: return default_res
        
        try:
            df = fdr.DataReader(f"KRX:{ticker}", self.start_str, self.end_str)
            if df.empty: df = fdr.DataReader(ticker, self.start_str, self.end_str)
            if df.empty: return default_res
            
            close_col = "Close" if "Close" in df.columns else "close"
            etf_returns = df[[close_col]].resample('W-FRI').last().pct_change(fill_method=None).dropna().rename(columns={close_col: 'ETF'})
            merged = pd.concat([etf_returns, self.bench_df], axis=1).dropna()
            
            if len(merged) < 20: return default_res
            
            X = merged[list(self.benchmarks.keys())]
            y = merged['ETF']
            ridge = Ridge(alpha=0.5, fit_intercept=True).fit(X, y)
            
            res = {factor: round(coef, 3) for factor, coef in zip(X.columns, ridge.coef_)}
            res["r_squared"] = round(ridge.score(X, y), 3)
            return res
        except:
            return default_res

# ==========================================
# 3. Pipeline
# ==========================================
class RefineryPipeline:
    def __init__(self):
        self.db_path = "data/registry/master_etf.db"
        self._init_db()
        self.struct_rules = StructuralRules()
        self.exp_rules = ExposureRules()
        self.stat_engine = StatisticalEngine()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS etf_structural (ticker TEXT PRIMARY KEY, name TEXT, asset_class TEXT, region TEXT, tax_treatment TEXT, pension_eligible INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS etf_exposure_vector (ticker TEXT PRIMARY KEY, growth REAL, value REAL, quality REAL, momentum REAL, size REAL, low_vol REAL, dividend REAL, duration REAL, inflation REAL, real_rate REAL, usd REAL, commodity REAL, gold REAL, oil REAL, kr_equity REAL, us_equity REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS etf_execution_profile (ticker TEXT PRIMARY KEY, execution_score_log REAL)''')
        # 🌟 통계적 팩터 벡터 전용 테이블
        c.execute('''CREATE TABLE IF NOT EXISTS etf_statistical_vector (ticker TEXT PRIMARY KEY, beta_mkt REAL, beta_growth REAL, beta_value REAL, beta_div REAL, beta_size REAL, beta_dur REAL, beta_gold REAL, beta_kor REAL, beta_usd REAL, r_squared REAL, updated_at TEXT)''')
        conn.commit()
        conn.close()

    def _upsert(self, df, table):
        if df.empty: return
        conn = sqlite3.connect(self.db_path)
        cols = ", ".join(df.columns)
        placeholders = ", ".join(["?"] * len(df.columns))
        updates = ", ".join([f"{col}=excluded.{col}" for col in df.columns if col != "ticker"])
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT(ticker) DO UPDATE SET {updates};"
        conn.executemany(sql, df.to_records(index=False))
        conn.commit()
        conn.close()

    def run(self):
        logging.info("🚀 하이브리드 엔진용 메타데이터 & 통계 DB 구축 시작...")
        universe = UnifiedProvider().fetch_universe()
        
        structs, exp_vecs, execs, stat_vecs = [], [], [], []
        today = datetime.today().strftime("%Y%m%d")
        
        for ticker, name in universe.items():
            # 1. 구조 및 정적 노출 (Rule-based)
            asset_class = self.struct_rules.classify_asset(name)
            region = "US" if "미국" in name else ("KR" if "200" in name or "국고채" in name else "GLOBAL")
            pension_eligible = 0 if ("(합성)" in name or "선물" in name or "레버리지" in name) else 1
            tax = "tax_free" if region == "KR" and asset_class == "equity" and pension_eligible else "taxable"
            
            structs.append({"ticker": ticker, "name": name, "asset_class": asset_class, "region": region, "tax_treatment": tax, "pension_eligible": pension_eligible})
            
            v = self.exp_rules.generate_base_vector(name, asset_class)
            if region == "US" and "(H)" not in name: v["usd"] = 1.0
            exp_vecs.append({"ticker": ticker, **v})
            
            # 가상 유동성 (Main 시스템 연동 전)
            execs.append({"ticker": ticker, "execution_score_log": round(np.random.uniform(10, 20), 2)})
            
            # 2. 🌟 통계적 노출 (Statistical Regression)
            stat = self.stat_engine.calculate_stat_vector(ticker)
            stat_vecs.append({"ticker": ticker, "updated_at": today, **stat})
            
        self._upsert(pd.DataFrame(structs), "etf_structural")
        self._upsert(pd.DataFrame(exp_vecs), "etf_exposure_vector")
        self._upsert(pd.DataFrame(execs), "etf_execution_profile")
        self._upsert(pd.DataFrame(stat_vecs), "etf_statistical_vector")
        logging.info("🎉 DB 구축 완료! 이제 quant.py를 실행하세요.")

if __name__ == "__main__":
    setup_environment()
    RefineryPipeline().run()