from fastapi import APIRouter, Query, Request


router = APIRouter()


@router.get("/recommend")
async def recommend_etfs(
    request: Request,
    query: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
):
    return request.app.state.etf_recommender.recommend(query, limit)
