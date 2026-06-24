import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import argparse
import asyncio
import logging
from typing import Any, Dict, Iterable, List

import chromadb
from dotenv import load_dotenv
from openai import AsyncOpenAI

from backend.fastapi_app.rag.embedder import QuantEmbedder
from data_pipeline.collectors.paper_collector import KciCollector
from data_pipeline.processors.paper_processor import PaperProcessor


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# httpx INFO 로그에는 KCI API key가 포함된 전체 요청 URL이 출력될 수 있다.
logging.getLogger("httpx").setLevel(logging.WARNING)

DEFAULT_QUERIES = [
    # 가치투자·저평가
    "가치주",
    "가치주 프리미엄",
    "가치주 초과수익률",
    "내재가치",
    "상대 가치평가",
    "저평가 이상현상",
    "가치 팩터",
    "PER PBR",
    "재무비율 주가수익률",
    "ROE 주가수익률",

    # 퀄리티·수익성
    "수익성 팩터",
    "수익성 이상현상",
    "영업현금흐름",
    "영업현금흐름 주가수익률",
    "이익 지속성",
    "퀄리티 프리미엄",
    "우량주 초과수익률",

    # 배당
    "배당수익률",

    # 모멘텀·시장 심리
    "주가 모멘텀",
    "가격 모멘텀",
    "모멘텀 초과수익률",
    "수익률 반전",
    "거래량 주가수익률",
    "이익수정비율",
    "어닝 서프라이즈",
    "투자자 심리 지수",
    "투자자 심리 주가수익률",

    # 안정성·방어주
    "주가 변동성",
    "저변동성 이상현상",
    "저변동성 포트폴리오",
    "고배당 저변동성",
    "재무 건전성",
    "재무 건전성 주가수익률",
    "꼬리 위험",
    "주식시장 꼬리위험",

    # 팩터·스마트베타
    "팩터 투자",
    "스마트 베타",
    "배당 스마트 베타",
    "기업규모 주가수익률",
    "부채비율 주가",
    "ESG 주가수익률",
    "금리 주가수익률",
    "환율 주식시장",
]


class ChromaHttpVectorStore:
    def __init__(self, client):
        self.client = client
        self.paper_collection = None
        self.inserted_count = 0

    async def init(self):
        self.paper_collection = await self.client.get_or_create_collection(
            name="paper_strategies",
            metadata={"hnsw:space": "cosine"},
        )

    async def add_papers_async(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ):
        if self.paper_collection is None:
            await self.init()

        await self.paper_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        self.inserted_count += len(ids)
        logger.info("[ChromaDB] %s paper chunks inserted", len(ids))

    async def add_fallback_paper(self, paper_id: str, title: str, abstract: str):
        await self.add_papers_async(
            ids=[f"{paper_id}_fallback_0"],
            embeddings=[[0.0] * 1536],
            documents=[f"paper title: {title}\nabstract: {abstract}"],
            metadatas=[
                {
                    "paper_id": paper_id,
                    "title": title,
                    "completeness": 0.0,
                    "source": "fallback",
                }
            ],
        )

    async def get_existing_paper_ids(self) -> set[str]:
        if self.paper_collection is None:
            await self.init()

        results = await self.paper_collection.get(include=["metadatas"])
        return {
            str(metadata["paper_id"])
            for metadata in (results.get("metadatas") or [])
            if metadata and metadata.get("paper_id")
        }

    async def count(self) -> int:
        if self.paper_collection is None:
            await self.init()
        return await self.paper_collection.count()


def _deduplicate_papers(papers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique = {}
    for paper in papers:
        paper_id = str(paper.get("paper_id") or "").strip()
        if paper_id and paper_id not in unique:
            unique[paper_id] = paper
    return list(unique.values())


async def collect_papers(
    collector: KciCollector,
    queries: List[str],
    per_query: int,
) -> List[Dict[str, Any]]:
    collected = []
    normalized_queries = list(dict.fromkeys(
        query.strip() for query in queries if query and query.strip()
    ))
    for index, query in enumerate(normalized_queries, 1):
        logger.info(
            "[Search %s/%s] query='%s', requested=%s",
            index,
            len(normalized_queries),
            query,
            per_query,
        )
        papers = await collector.search_quant_papers(query=query, limit=per_query)
        collected.extend(papers)
        logger.info(
            "[Search %s/%s] parsed=%s, unique-so-far=%s",
            index,
            len(normalized_queries),
            len(papers),
            len(_deduplicate_papers(collected)),
        )
    return _deduplicate_papers(collected)


async def run_kci_ingestion(
    queries: List[str] | None = None,
    per_query: int = 10,
    max_papers: int = 100,
):
    load_dotenv()
    kci_api_key = os.getenv("KCI_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not kci_api_key or not openai_api_key:
        missing = [
            name
            for name, value in (
                ("KCI_API_KEY", kci_api_key),
                ("OPENAI_API_KEY", openai_api_key),
            )
            if not value
        ]
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    logger.info("[Ingestion] Starting KCI paper ingestion pipeline")

    chroma_client = await chromadb.AsyncHttpClient(host="127.0.0.1", port=8002)
    vector_store = ChromaHttpVectorStore(chroma_client)
    await vector_store.init()

    openai_client = AsyncOpenAI(
        api_key=openai_api_key,
        base_url="https://gms.ssafy.io/gmsapi/api.openai.com/v1/"
    )
    embedder = QuantEmbedder(client=openai_client)
    processor = PaperProcessor(openai_client, embedder, vector_store)
    kci_collector = KciCollector(api_key=kci_api_key)

    selected_queries = queries or DEFAULT_QUERIES
    papers = await collect_papers(
        collector=kci_collector,
        queries=selected_queries,
        per_query=per_query,
    )

    if not papers:
        logger.warning("No papers found. Stopping pipeline.")
        return

    existing_paper_ids = await vector_store.get_existing_paper_ids()
    unstored_papers = [
        paper for paper in papers
        if str(paper.get("paper_id")) not in existing_paper_ids
    ]
    new_papers = unstored_papers[:max_papers]
    already_stored_count = len(papers) - len(unstored_papers)
    deferred_count = len(unstored_papers) - len(new_papers)

    logger.info(
        "[Ingestion] collected unique=%s, already stored=%s, processing new=%s, deferred by limit=%s",
        len(papers),
        already_stored_count,
        len(new_papers),
        deferred_count,
    )

    if not new_papers:
        logger.info("[Ingestion] No new papers to process")
        return

    before_total = await vector_store.count()
    for i, paper in enumerate(new_papers):
        title = paper.get("title", f"Unknown_Title_{i}")
        abstract = paper.get("abstract", "")

        if not abstract:
            logger.warning("Skipping paper with empty abstract: %s", title)
            continue

        paper_meta = {
            "paperId": paper.get("paper_id", f"kci_{i}"),
            "title": title,
        }

        logger.info("[%s/%s] Extracting and storing: %s", i + 1, len(new_papers), title)
        before_inserted_count = vector_store.inserted_count
        await processor.extract_and_store(chunk_text=abstract, paper_meta=paper_meta)

        if vector_store.inserted_count == before_inserted_count:
            logger.warning("No strategy rows produced for '%s'. Inserting fallback abstract record.", title)
            await vector_store.add_fallback_paper(
                paper_id=paper_meta["paperId"],
                title=title,
                abstract=abstract,
            )

    after_total = await vector_store.count()
    logger.info(
        "[Ingestion] Finished: collection chunks %s -> %s (+%s)",
        before_total,
        after_total,
        after_total - before_total,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect KCI papers into ChromaDB")
    parser.add_argument(
        "--per-query",
        type=int,
        default=10,
        help="각 검색어에서 요청할 논문 수 (기본 10)",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=100,
        help="이번 실행에서 LLM 처리할 신규 논문 최대 수 (기본 100)",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        help="기본 검색어 대신 사용할 검색어 목록",
    )
    args = parser.parse_args()

    asyncio.run(
        run_kci_ingestion(
            queries=args.queries,
            per_query=max(1, args.per_query),
            max_papers=max(1, args.max_papers),
        )
    )
