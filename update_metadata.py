import logging
from data_engineering.repository.etf_repository import MemoryETFRepository
from data_engineering.providers.kodex_provider import KodexProvider
from data_engineering.providers.naver_provider import NaverETFProvider
from core.korea_etf_mapper import KoreaETFMapper

# 로깅 설정 (진행 상황을 눈으로 보기 위함)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

if __name__ == "__main__":
    print("\n========================================================")
    print(" 🔄 ETF 메타데이터 수집 파이프라인 가동 (Data Engineering)")
    print("========================================================\n")
    
    # 1. Repository 및 Provider 세팅
    repo = MemoryETFRepository()
    providers = [NaverETFProvider()] # naver 크롤러 주입
    
    # 2. 파이프라인 엔진 생성 및 수집 시작
    mapper = KoreaETFMapper(providers=providers, repository=repo)
    mapper.update_metadata() # 이 때 실제 requests 통신 및 파싱이 일어납니다.
    
    print("\n========================================================")
    print(" ✅ 수집 완료 및 Repository 상태 확인")
    print("========================================================")
    
    # 3. 크롤링 결과물 확인
    # Repository 내부에 안전하게 적재된 전체 데이터 스냅샷을 가져옵니다.
    # get_all() 이 구현되어 있지 않다면 임시로 repo._db 를 출력하셔도 됩니다.
    db_snapshot = repo._db if hasattr(repo, '_db') else {}
    
    print(f"총 {len(db_snapshot)}개의 ETF가 성공적으로 적재되었습니다.\n")
    
    # 대표적인 ETF 2개만 샘플로 출력해보기
    test_tickers = ["304940", "280930"] # KODEX 미국나스닥100(H), KODEX 미국러셀2000(H)
    
    for ticker in test_tickers:
        sample = repo.get_etf(ticker)
        if sample:
            print(f"[{ticker}] {sample['name']} | 보수: {sample['fee']*100:.3f}% | Provider: {sample['provider']} | 최근확인: {sample['last_seen_at']}")
        else:
            print(f"[{ticker}] 데이터를 찾을 수 없습니다.")