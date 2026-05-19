import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from abc import ABC, abstractmethod
from typing import List, Any
from data_engineering.dto.etf_dto import ETFMetadata

class BaseETFProvider(ABC):
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.logger = logging.getLogger(f"Provider_{self.name}")
        
        self.session = requests.Session()
        # 멱등성이 보장된 GET 메서드에 한해서만 재시도(Fault Tolerance)
        retry_strategy = Retry(
            total=3, connect=3, read=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def fetch_metadata(self) -> List[ETFMetadata]:
        """Template Method: 네트워크 레이어와 파싱 레이어의 실행 흐름 통제"""
        try:
            self.logger.info(f"[{self.name}] 메타데이터 동기화 시작...")
            raw_data = self._fetch_raw_data()
            parsed_data = self._parse(raw_data)
            self.logger.info(f"[{self.name}] 파싱 완료 (총 {len(parsed_data)}개 종목 추출)")
            return parsed_data
        except Exception:
            self.logger.exception(f"[{self.name}] 메타데이터 파싱 또는 통신 중 치명적 에러")
            return []

    @abstractmethod
    def _fetch_raw_data(self) -> Any: pass

    @abstractmethod
    def _parse(self, raw_data: Any) -> List[ETFMetadata]: pass