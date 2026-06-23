import httpx
import logging
# import xmltodict # KCI XML 파싱용 (pip install xmltodict 필요)
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class KciCollector:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # KCI Open API 논문검색 엔드포인트 (실제 API 명세서 확인 필수)
        self.base_url = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"

    async def search_quant_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """KCI API를 통해 국문 퀀트/재무 논문 메타데이터와 초록 수집"""
        params = {
            "apiCode": "articleSearch",
            "key": self.api_key,
            "title": query,
            "displayCount": limit
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params, timeout=15.0)
                response.raise_for_status()
                
                # 1. XML 문자열을 파이썬이 읽을 수 있게 트리 구조로 변환
                root = ET.fromstring(response.text)
                papers = []
                
                # 2. XML에서 <record> 태그를 모두 찾아서 순회
                for record in root.findall('.//record'):
                    # 논문 고유 ID 추출 (<articleInfo article-id="...">)
                    article_info = record.find('.//articleInfo')
                    paper_id = article_info.get('article-id') if article_info is not None else "unknown_id"
                    
                    # 제목 추출 (<article-title>)
                    title_elem = record.find('.//article-title')
                    title = title_elem.text if title_elem is not None else "제목 없음"
                    
                    # 초록 추출 (<abstract>)
                    abstract_elem = record.find('.//abstract')
                    abstract = abstract_elem.text if abstract_elem is not None else ""
                    
                    # 3. 초록이 존재하는 '진짜' 논문만 리스트에 담기
                    if abstract and abstract.strip():
                        papers.append({
                            "paper_id": paper_id,
                            "title": title,
                            "abstract": abstract.strip()
                        })
                
                logger.info(f"✅ [KCI Collector] '{query}' 검색 완료 (실제 논문 {len(papers)}건 파싱 성공)")
                return papers

            except httpx.HTTPError as e:
                logger.error(f"🚨 [KCI Collector Error] KCI API 호출 실패: {e}")
                return []