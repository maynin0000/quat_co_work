import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import asyncio
import logging
from typing import Any, Dict, List

import chromadb
from dotenv import load_dotenv
from openai import AsyncOpenAI

from backend.fastapi_app.rag.embedder import QuantEmbedder
from data_pipeline.collectors.paper_collector import KciCollector
from data_pipeline.processors.paper_processor import PaperProcessor


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


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


async def run_kci_ingestion():
    load_dotenv()
    kci_api_key = os.getenv("KCI_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not kci_api_key or not openai_api_key:
        logger.error("KCI_API_KEY or OPENAI_API_KEY is missing from .env")
        return

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

    search_query = "\uc8fc\uc2dd \uc218\uc775\ub960"
    logger.info("Searching KCI with query: %s", search_query)

    papers = await kci_collector.search_quant_papers(query=search_query, limit=3)

    if not papers:
        logger.warning("No papers found. Stopping pipeline.")
        return

    for i, paper in enumerate(papers):
        title = paper.get("title", f"Unknown_Title_{i}")
        abstract = paper.get("abstract", "")

        if not abstract:
            logger.warning("Skipping paper with empty abstract: %s", title)
            continue

        paper_meta = {
            "paperId": paper.get("paper_id", f"kci_{i}"),
            "title": title,
        }

        logger.info("[%s/%s] Extracting and storing: %s", i + 1, len(papers), title)
        before_inserted_count = vector_store.inserted_count
        await processor.extract_and_store(chunk_text=abstract, paper_meta=paper_meta)

        if vector_store.inserted_count == before_inserted_count:
            logger.warning("No strategy rows produced for '%s'. Inserting fallback abstract record.", title)
            await vector_store.add_fallback_paper(
                paper_id=paper_meta["paperId"],
                title=title,
                abstract=abstract,
            )

    logger.info("[Ingestion] Finished")


if __name__ == "__main__":
    asyncio.run(run_kci_ingestion())
