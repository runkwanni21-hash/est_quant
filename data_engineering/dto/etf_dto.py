from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class ETFMetadata(BaseModel):
    """
    Pydantic 기반 ETF 메타데이터 검증 DTO (불변 객체로 해싱 및 스레드 안정성 확보)
    """
    model_config = ConfigDict(frozen=True)

    # 종목코드는 반드시 6자리 숫자여야 함
    ticker: str = Field(..., pattern=r"^[0-9A-Z]{6}$", description="종목코드 6자리")
    
    # 총보수는 0~10% 사이의 실수
    fee: float = Field(..., ge=0.0, le=0.10, description="총보수 (0~10%)")
    
    name: str
    provider: str
    is_active: bool = True
    last_seen_at: datetime = Field(default_factory=datetime.now)
    
    # 향후 확장을 위한 Nullable 필드
    leverage: Optional[int] = None
    currency_hedged: Optional[bool] = None