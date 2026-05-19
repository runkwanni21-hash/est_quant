import requests
import re
from typing import List, Dict, Any
from .base_provider import BaseETFProvider
from data_engineering.dto.etf_dto import ETFMetadata
from data_engineering.normalizers.etf_name_normalizer import ETFNameNormalizer

class NaverETFProvider(BaseETFProvider):
    """네이버 금융 ETF 데이터를 활용한 KODEX, TIGER ETF 크롤러"""
    
    def __init__(self) -> None:
        super().__init__(name="NAVER_ETF")
        # 네이버 금융 ETF 전체 리스트 API
        self.url = "https://finance.naver.com/api/sise/etfItemList.nhn"

    def _fetch_raw_data(self) -> Dict[str, Any]:
        """네이버 API로부터 JSON 데이터 취득"""
        response = self.session.get(self.url, timeout=10)
        response.raise_for_status()
        return response.json()

    def _parse(self, raw_data: Dict[str, Any]) -> List[ETFMetadata]:
        result: List[ETFMetadata] = []
        
        # 네이버 API 응답 구조: result -> etfItemList
        etf_list = raw_data.get("result", {}).get("etfItemList", [])
        
        # 특정 운용사만 필터링 (KODEX, TIGER)
        target_providers = ["KODEX", "TIGER","ACE"]
        
        for item in etf_list:
            raw_name: str = item.get("itemname", "")
            
            # 운용사 필터링 (이름에 포함된 경우)
            if not any(provider in raw_name for provider in target_providers):
                continue
                
            ticker: str = item.get("itemcode", "")
            # 네이버 API는 보수 정보가 포함되지 않으므로, 
            # 필요 시 상세 페이지를 추가 크롤링하거나, 별도 DB 매핑 필요
            
            try:
                # 1. 정규화
                clean_name = ETFNameNormalizer.normalize(raw_name)
                
                # 2. DTO 생성
                metadata = ETFMetadata(
                    ticker=ticker,
                    name=clean_name,
                    fee=0.0,  # 네이버 목록 API상 보수 미제공
                    provider=self._detect_provider(raw_name)
                )
                result.append(metadata)
            except Exception as e:
                self.logger.warning(f"[{self.name}] {ticker} 파싱 실패: {e}")
                    
        return result

    def _detect_provider(self, name: str) -> str:
        if "KODEX" in name: return "KODEX"
        if "TIGER" in name: return "TIGER"
        return "UNKNOWN"