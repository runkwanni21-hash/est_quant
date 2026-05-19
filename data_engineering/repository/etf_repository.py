import threading
import copy
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from data_engineering.dto.etf_dto import ETFMetadata

class BaseETFRepository(ABC):
    """데이터 저장소 추상화 인터페이스 (OCP 준수)"""
    @abstractmethod
    def upsert(self, etf: ETFMetadata) -> None: pass
    
    @abstractmethod
    def bulk_upsert(self, etfs: List[ETFMetadata]) -> None: pass

    @abstractmethod
    def get_etf(self, ticker: str) -> Optional[Dict[str, Any]]: pass

    @abstractmethod
    def find_candidates(self, target_factor: str, target_tier: str) -> Dict[str, Dict[str, Any]]: pass

class MemoryETFRepository(BaseETFRepository):
    """In-Memory 기반 Thread-Safe 저장소"""
    
    def __init__(self, initial_data: Optional[Dict[str, Any]] = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._db: Dict[str, Any] = initial_data or {}
        # 재진입 가능(Re-entrant) Lock: 헬퍼 함수 간 데드락 방지
        self._lock = threading.RLock()

    def upsert(self, etf: ETFMetadata) -> None:
        with self._lock:
            self._upsert_internal(etf)

    def bulk_upsert(self, etfs: List[ETFMetadata]) -> None:
        """한 Provider의 결과물을 일괄 반영하며, 중간 실패 시 Rollback (All-or-Nothing)"""
        with self._lock:
            backup = copy.deepcopy(self._db) # Rollback을 위한 메모리 스냅샷
            try:
                for etf in etfs:
                    self._upsert_internal(etf)
            except Exception as e:
                self.logger.error(f"Bulk Upsert 중 오류 발생. Rollback을 수행합니다: {e}")
                self._db = backup 
                raise

    def _upsert_internal(self, etf: ETFMetadata) -> None:
        """실제 Upsert 비즈니스 로직 (반드시 Lock Context 내에서만 호출)"""
        existing = self._db.get(etf.ticker, {})
        updated_data = {
            **existing,
            "name": etf.name,
            "fee": etf.fee,
            "provider": etf.provider,
            "is_active": etf.is_active,
            "last_seen_at": etf.last_seen_at
        }
        # 신규 발견된 자산일 경우 기본 포트폴리오 뼈대 구성
        if "vector" not in updated_data:
            updated_data["tier"] = "unclassified"
            updated_data["vector"] = {}
            
        self._db[etf.ticker] = updated_data

    def get_etf(self, ticker: str) -> Optional[Dict[str, Any]]:
        """단일 종목 조회 (원본 오염 방지를 위한 Deepcopy)"""
        with self._lock:
            data = self._db.get(ticker)
            return copy.deepcopy(data) if data else None

    def find_candidates(self, target_factor: str, target_tier: str) -> Dict[str, Dict[str, Any]]:
        """Mapper의 조건에 맞는 종목 필터링 (Query Interface 캡슐화)"""
        with self._lock:
            candidates = {
                ticker: copy.deepcopy(data) 
                for ticker, data in self._db.items() 
                if data.get("tier") == target_tier and target_factor in data.get("vector", {})
            }
            return candidates