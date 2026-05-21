import pandas as pd
import numpy as np
import lightgbm as lgb
import copy
import os
import joblib
from sklearn.multioutput import MultiOutputRegressor
from typing import List, Dict, Any, Optional
from .base_model import QuantitativeModel

class LightGBMMIMOMacroModel(QuantitativeModel):
    # 🌟 [수정] 기본 이름을 AutoTrade 규격인 "Macro_AI"로 복구
    def __init__(self, name: str = "Macro_AI", train_window: int = 2000, 
                 target_cols: Optional[List[str]] = None, feature_builder=None) -> None:
        super().__init__(name)
        self.train_window = train_window
        self.target_cols = target_cols if target_cols else [
            "macro_growth", "macro_inflation", "macro_liquidity", "macro_stress"
        ]
        self.feature_builder = feature_builder
        
        base_model = lgb.LGBMRegressor(
            n_estimators=150, learning_rate=0.03, max_depth=5, 
            min_child_samples=40, random_state=42, verbose=-1, objective='huber'
        )
        self.model = MultiOutputRegressor(base_model)
        
        self.feature_cols: List[str] = []
        self.latest_states: Dict[str, float] = {} 
        self.latest_confidence: Dict[str, float] = {} 
        self.ema_states: Dict[str, float] = {}
        self.ema_alpha: float = 0.15

    def fit(self, data: pd.DataFrame) -> None:
        df_feat = self.feature_builder.process(data, is_training=True)
        exclude = ["Open", "High", "Low", "Close", "Volume"] + self.target_cols
        self.feature_cols = [c for c in df_feat.columns if c not in exclude and not c.startswith("Close_")]
        
        train_data = df_feat.dropna(subset=self.target_cols + self.feature_cols).iloc[-self.train_window:]
        self.model.fit(train_data[self.feature_cols], train_data[self.target_cols].values)
        self.is_fitted = True

    def update(self, data: pd.DataFrame, candidate_mode: bool = False, candidate_name: Optional[str] = None) -> None:
        if not self.is_fitted:
            self.fit(data)
            return

        df_feat = self.feature_builder.process(data, is_training=True)
        train_data = df_feat.dropna(subset=self.target_cols + self.feature_cols).iloc[-self.train_window:]
        if len(train_data) < 50: return
        self.model.fit(train_data[self.feature_cols], train_data[self.target_cols].values)
        self.is_fitted = True

    def predict(self, data: pd.DataFrame) -> Dict[str, Any]:
        if not self.is_fitted: return {}
        
        # 1. 피처 데이터 전처리
        df_feat = self.feature_builder.process(data, is_training=False)
        
        # 🛡️ [방어코드 1] 로드 오류 등으로 피처 컬럼 정보가 날아간 경우
        if not getattr(self, "feature_cols", []):
            print(f"🚨 [{self.name}] 피처 컬럼(feature_cols) 정보가 없습니다. 모델 재학습이 필요합니다.")
            return {}

        latest_X = df_feat[self.feature_cols].iloc[-1:]
        
        # 🛡️ [방어코드 2] 빈 데이터프레임 방어 (IndexError 원인 차단)
        if latest_X.empty:
            print(f"🚨 [{self.name}] 전처리된 피처 데이터가 비어있습니다.")
            return {}

        # 🛡️ [방어코드 3] dict 변환 시 안전하게 할당
        records = latest_X.to_dict("records")
        if records:
            self.latest_features = records[0]

        # 이후 예측 로직 진행... (기존 코드 유지)
        preds = np.clip(self.model.predict(latest_X)[0], -1.0, 1.0)
        self.latest_states, self.latest_confidence = {}, {}
        
        for idx, target_name in enumerate(self.target_cols):
            val = float(preds[idx])
            self.latest_states[target_name] = val
            self.latest_confidence[target_name] = abs(val)
            
            if target_name not in self.ema_states:
                self.ema_states[target_name] = val
            else:
                self.ema_states[target_name] = (self.ema_states[target_name] * (1 - self.ema_alpha)) + (val * self.ema_alpha)
            
        return {"states": self.ema_states, "confidences": self.latest_confidence}


    # 🌟 부모 클래스(QuantitativeModel)의 규격을 100% 준수하는 Save / Load 오버라이드
    def save(self, folder_path: str = "checkpoints") -> None:
        if not self.is_fitted: 
            return
        if not os.path.exists(folder_path): 
            os.makedirs(folder_path)
            
        filepath = os.path.join(folder_path, f"{self.name}.pkg")
        
        # self.model만 저장하는 것이 아니라, feature_cols 상태 유지를 위해 객체 전체를 저장
        joblib.dump(self, filepath)
        print(f"💾 [{self.name}] 실전 배포용 모델 객체 추출 완료: {filepath}")

    @classmethod
    def load(cls, file_path: str) -> 'QuantitativeModel':
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"❌ 모델 파일 찾을 수 없음: {file_path}")
            
        # 객체 전체를 안전하게 로드
        model_instance = joblib.load(file_path)
        
        # 🛡️ 하위 호환성 검증: 과거 방식(dict 등)으로 잘못 저장된 껍데기 파일 방어
        if not hasattr(model_instance, 'feature_cols') or not model_instance.feature_cols:
            print(f"⚠️ [{getattr(model_instance, 'name', 'Unknown')}] 피처 정보가 손상되었습니다. 새로 학습이 필요합니다.")
            
        print(f"📂 [{getattr(model_instance, 'name', 'Unknown')}] 모델 객체 로드 완료")
        return model_instance

    def get_raw_macro_vector(self) -> Dict[str, float]:
        if not self.ema_states: return {}
        g, i = self.ema_states.get("macro_growth", 0.0), self.ema_states.get("macro_inflation", 0.0)
        l, s = self.latest_states.get("macro_liquidity", 0.0), self.ema_states.get("macro_stress", 0.0)

        base = {"equity": 0.40, "income": 0.15, "bond": 0.35, "commodity": 0.05, "cash": 0.05}
        
        inc_tilt = (g * 0.10) + (i * 0.10) + (l * 0.05) - (max(0, s) * 0.10)
        eq_tilt = (g * 0.30) + (l * 0.20) - (max(0, s) * 0.35) - (i * 0.10)
        bd_tilt = -(g * 0.10) - (i * 0.20) + (max(0, s) * 0.20)
        cmd_tilt = (i * 0.20) + (max(0, s) * 0.05) - (g * 0.05)
        cash_tilt = max(0.0, np.tanh(s * 2.0)) * 0.35 - (l * 0.05)
        
        cash_target = max(0.05, min(1.0, base["cash"] + cash_tilt))
        risky_budget = 1.0 - cash_target

        risky_vector = {
            "equity": max(0.0, base["equity"] + eq_tilt),
            "income": max(0.0, base["income"] + inc_tilt),
            "bond": max(0.0, base["bond"] + bd_tilt),
            "commodity": max(0.0, base["commodity"] + cmd_tilt)
        }
        
        risky_sum = sum(risky_vector.values())
        if risky_sum > 0:
            for k in risky_vector: risky_vector[k] = (risky_vector[k] / risky_sum) * risky_budget
        else:
            for k in risky_vector: risky_vector[k] = 0.0
                
        vector = risky_vector.copy()
        vector["cash_target"] = cash_target
        return vector

    def print_diagnostics(self) -> None:
        if not self.ema_states: return
        print("\n🧠 [Latent Macro State Diagnostics (EMA Smoothed)]")
        for target, val in self.ema_states.items():
            conf = self.latest_confidence.get(target, 0.0)
            bar_len = 12
            filled = max(0, min(bar_len, int((val + 1.0) / 2.0 * bar_len)))
            bar = "[" + "=" * filled + " " * (bar_len - filled) + "]"
            print(f"  └ {target[6:].upper():<10} | EMA Score: {val:+.3f} {bar} | Conf: {conf:.2f}")

    # 🌟 [수정] 확장자를 AutoTrade 규격인 .pkg로 복구
    def save(self, directory: str) -> None:
        if not self.is_fitted: return
        if not os.path.exists(directory): os.makedirs(directory)
        filepath = os.path.join(directory, f"{self.name}.pkg")
        joblib.dump(self.model, filepath)
        print(f"💾 [{self.name}] 실전 배포용 모델 추출 완료: {filepath}")

    # 🌟 [수정] 확장자를 AutoTrade 규격인 .pkg로 복구
    def load(self, directory: str) -> None:
        filepath = os.path.join(directory, f"{self.name}.pkg")
        if os.path.exists(filepath):
            self.model = joblib.load(filepath)
            self.is_fitted = True
        else:
            raise FileNotFoundError(f"❌ 모델 파일 찾을 수 없음: {filepath}")

    # 🌟 [수정] 기존 AutoTrade 규격 호환을 위한 임기응변 로직 복구
    def get_signal(self) -> float: 
        g = self.ema_states.get("macro_growth", 0.0)
        s = self.ema_states.get("macro_stress", 0.0)
        return float(np.clip(g - s, -1.0, 1.0))
    
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from typing import Dict, Any, List
from .base_model import QuantitativeModel

class LightGBMMultiRegimeModel(QuantitativeModel):
    def __init__(self, name: str = "LGBM_Macro_AI", train_window: int = 2000, 
                 target_col: str = "target_regime", feature_builder: Any = None, 
                 calib_method: str = "sigmoid") -> None:
        super().__init__(name)
        self.train_window: int = train_window
        self.target_col: str = target_col
        self.feature_builder = feature_builder
        
        base_model = lgb.LGBMClassifier(
            n_estimators=150, learning_rate=0.05, max_depth=5, 
            min_child_samples=40, random_state=42, verbose=-1,
            class_weight='balanced'
        )
        
        tscv = TimeSeriesSplit(n_splits=5)
        self.model = CalibratedClassifierCV(estimator=base_model, method=calib_method, cv=tscv)
        
        self.feature_cols: List[str] = []
        self.latest_probs: Dict[str, float] = {}
        self.latest_confidence: float = 0.0

    def fit(self, data: pd.DataFrame) -> None:
        """데이터를 받아 모델을 롤링 학습시킵니다."""
        df_feat = self.feature_builder.process(data, is_training=True)
        exclude = ["Open", "High", "Low", "Close", "Volume", self.target_col]
        
        # 종가(Close_)와 불필요한 기본 컬럼을 제외하고 순수 피처만 선택
        self.feature_cols = [c for c in df_feat.columns if c not in exclude and not c.startswith("Close_")]
        
        # 타겟과 피처 모두 결측치가 없는 데이터만 훈련에 사용
        train_data = df_feat.dropna(subset=[self.target_col] + self.feature_cols).iloc[-self.train_window:]
        X_train = train_data[self.feature_cols]
        y_train = train_data[self.target_col].values
        
        if len(X_train) > 50: # 최소 훈련 샘플 확보 시에만 학습
            self.model.fit(X_train, y_train)
            self.is_fitted = True

    def predict(self, data: pd.DataFrame) -> Dict[str, Any]:
        """주어진 데이터를 기반으로 Bear, Neutral, Bull 확률을 반환합니다."""
        if not self.is_fitted: 
            return {"Bear_Prob": 0.33, "Neutral_Prob": 0.34, "Bull_Prob": 0.33}
            
        df_feat = self.feature_builder.process(data, is_training=False)
        latest_X = df_feat[self.feature_cols].iloc[-1:]
        
        # 모델 예측
        probs = self.model.predict_proba(latest_X)[0]
        
        # 클래스가 3개(0: Bear, 1: Neutral, 2: Bull)인 경우에 대한 매핑
        if len(probs) >= 3:
            self.latest_probs = {
                "Bear_Prob": float(probs[0]), 
                "Neutral_Prob": float(probs[1]), 
                "Bull_Prob": float(probs[2])
            }
        else:
            self.latest_probs = {"Bear_Prob": 0.33, "Neutral_Prob": 0.34, "Bull_Prob": 0.33}
        
        # 확신도(Confidence) 계산: 1등 확률 - 2등 확률
        sorted_probs = sorted(self.latest_probs.values(), reverse=True)
        self.latest_confidence = float(sorted_probs[0] - sorted_probs[1])
        
        return self.latest_probs

    def get_signal(self) -> int:
        """
        [상속 규약 준수] 
        최종적으로 롱(2), 중립(1), 숏(0) 형태의 인트형 시그널을 반환합니다.
        """
        min_confidence = 0.10
        if not self.latest_probs: 
            return 1 # 기본 중립
            
        max_state = max(self.latest_probs, key=self.latest_probs.get)
        
        # 확신도가 너무 낮으면 중립 유지
        if self.latest_confidence < min_confidence: 
            return 1 
            
        if max_state == "Bull_Prob": 
            return 2
        elif max_state == "Bear_Prob": 
            return 0
        else: 
            return 1