from fastapi import APIRouter, Query, Request


router = APIRouter()


@router.get("/strategies")
async def list_strategies(
    request: Request,
    query: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=10),
    asset_type: str = Query(default="stock", pattern="^(stock|etf)$"),
):
    repo = request.app.state.strategy_repo
    if query.strip():
        payload = repo.recommend(query, limit, asset_type)
        try:
            embeddings = await request.app.state.embedder.get_embeddings([query])
            if embeddings:
                papers = await request.app.state.vector_store.search_papers_async(
                    query_embedding=embeddings[0],
                    n_results=5,
                    min_completeness=80.0,
                )
                documents = (papers.get("documents") or [[]])[0]
                metadatas = (papers.get("metadatas") or [[]])[0]
                payload["paper_evidence"] = [
                    {
                        "title": (metadata or {}).get("title", "KCI 논문"),
                        "summary": document,
                    }
                    for document, metadata in zip(documents, metadatas)
                ]
        except Exception:
            payload["paper_evidence"] = []
        return payload
    payload = repo.load_etf() if asset_type == "etf" else repo.load()
    payload["strategies"] = (payload.get("strategies") or [])[:limit]
    return payload
