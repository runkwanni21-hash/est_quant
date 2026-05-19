import re

class ETFNameNormalizer:
    """운용사별로 상이한 ETF 명칭 표기법을 표준 스키마로 정규화합니다."""
    
    @staticmethod
    def normalize(name: str) -> str:
        if not name:
            raise ValueError("ETF 이름은 비어있을 수 없습니다.")
        
        v: str = name.strip()
        # 다중 공백 제거 및 괄호 기호 표준화
        v = re.sub(r'\s+', ' ', v)
        v = v.replace(" (H)", "(H)").replace(" (합성)", "(합성)")
        
        return v