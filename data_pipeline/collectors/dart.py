import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class DartCollector:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # DART 단일회사 주요계정 API (재무제표)
        self.base_url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

    async def fetch_financial_data(self, corp_code: str, bsns_year: str, reprt_code: str = "11011") -> Dict[str, Any]:
        """
        특정 기업의 특정 연도/분기 재무 데이터를 수집
        - corp_code: DART 고유번호 (8자리)
        - reprt_code: 11011(사업보고서), 11012(반기), 11013(1분기), 11014(3분기)
        """
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "000": # 정상 응답
                    logger.info(f"✅ [DART Collector] 기업코드 {corp_code} ({bsns_year}) 재무데이터 수집 완료")
                    
                    # API 응답(리스트 형태)을 Dict로 가공해서 리턴
                    # 여기서 가공된 raw 딕셔너리가 우리가 만든 normalizer.py의 
                    # normalize_dart_response() 함수로 들어가게 됨!
                    raw_dict = self._parse_dart_list_to_dict(data.get("list", []))
                    return raw_dict
                else:
                    logger.warning(f"⚠ [DART Collector] 데이터 없음: {data.get('message')}")
                    return {}
            except httpx.HTTPError as e:
                logger.error(f"🚨 [DART Collector Error] DART API 호출 실패: {e}")
                return {}

    def _parse_dart_list_to_dict(self, dart_list: list) -> dict:
        """DART의 key-value 배열 응답을 우리가 쓰기 편한 dict로 변환"""
        result = {}
        for item in dart_list:
            account_nm = item.get("account_nm")  # 예: "자산총계", "자본총계", "매출액"
            amount = item.get("thstrm_amount")   # 당기 금액
            if account_nm and amount:
                result[account_nm] = amount
        return result