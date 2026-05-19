import re
from bs4 import BeautifulSoup
from typing import List
from .base_provider import BaseETFProvider
from data_engineering.dto.etf_dto import ETFMetadata
from data_engineering.normalizers.etf_name_normalizer import ETFNameNormalizer

class KodexProvider(BaseETFProvider):
    """삼성자산운용(KODEX) 전용 메타데이터 크롤러"""
    
    # DOM 변경 시 쉽게 대응하기 위한 Selector 중앙화(Versioning 대응 가능)
    SELECTORS = {
        "v1": {
            "product_row": ".product-list table tbody tr",
            "ticker": ".ticker",
            "name": ".name a",
            "fee": ".fee"
        }
    }
    
    def __init__(self, selector_version: str = "v1") -> None:
        super().__init__(name="KODEX")
        self.url = "https://www.samsungfund.com/etf/product/list.do"
        self.selectors = self.SELECTORS[selector_version]

    def _fetch_raw_data(self) -> str:
        response = self.session.get(self.url, timeout=10)
        response.raise_for_status()
        return response.text

    def _parse(self, raw_data: str) -> List[ETFMetadata]:
        result: List[ETFMetadata] = []
        soup = BeautifulSoup(raw_data, "html.parser")
        product_list = soup.select(self.selectors["product_row"])
        
        for item in product_list:
            ticker_tag = item.select_one(self.selectors["ticker"])
            name_tag = item.select_one(self.selectors["name"])
            fee_tag = item.select_one(self.selectors["fee"])
            
            if ticker_tag and name_tag:
                ticker: str = re.sub(r'[^0-9]', '', ticker_tag.text.strip())
                
                # 1. 분리된 정규화(Normalization) 엔진 사용
                raw_name: str = name_tag.text.strip()
                clean_name: str = ETFNameNormalizer.normalize(raw_name)
                
                fee_str: str = fee_tag.text.replace("%", "").strip() if fee_tag else "0.0"
                try:
                    fee: float = float(fee_str) / 100.0
                except ValueError:
                    fee = 0.0

                # 2. Pydantic DTO를 통한 자동 Validation
                try:
                    metadata = ETFMetadata(
                        ticker=ticker,
                        name=clean_name,
                        fee=fee,
                        provider=self.name
                    )
                    result.append(metadata)
                except ValueError as ve:
                    self.logger.warning(f"[{self.name}] {ticker} 유효성 검사 실패 (skip): {ve}")
                    
        return result