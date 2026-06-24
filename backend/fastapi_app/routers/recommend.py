import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from fastapi.encoders import jsonable_encoder  # 🚨 이거 추가!
from shared.schemas.recommendation import RecommendationRequest

logger = logging.getLogger(__name__)
router = APIRouter()

async def recommend_stream_generator(request: Request, user_req: RecommendationRequest):
    """
    프론트엔드로 분석 진행 상태와 최종 결과를 청크 단위로 스트리밍 (SSE)
    - 실제 QuantRecommender 로직과 연동 완료
    """
    try:
        # 1. 의존성 객체 로드 (main.py에서 app.state에 등록했다고 가정)
        # 만약 Depends를 사용중이라면 파라미터로 주입받는 방식으로 변경해도 무방함
        embedder = getattr(request.app.state, "embedder", None)
        recommender = getattr(request.app.state, "recommender", None)

        if not embedder or not recommender:
            raise RuntimeError("서버 내부 객체(Embedder/Recommender)가 초기화되지 않았습니다.")

        # 상태 1: 임베딩 시작
        yield f"data: {json.dumps({'status': 'processing', 'message': '질문 의도 파악 및 벡터 변환 중...'})}\n\n"
        
        # 임베딩 생성 (리스트 형태로 넣고 첫 번째 결과값 추출)
        query_embeddings = await embedder.get_embeddings([user_req.user_input])
        if not query_embeddings:
            raise ValueError("임베딩 생성에 실패했습니다.")
        embedding_vector = query_embeddings[0]

        # 상태 2: 교차 분석 시작
        yield f"data: {json.dumps({'status': 'processing', 'message': 'RAG 논문 DB 및 정형 재무 DB 교차 검색 중...'})}\n\n"
        
        # 우리가 만든 하이브리드 추천 엔진 가동!
        recommendations = await recommender.generate_recommendation(
            user_query=user_req.user_input,
            query_embedding=embedding_vector,
            top_n=user_req.top_n
        )

        # 상태 3: 최종 포장
        yield f"data: {json.dumps({'status': 'processing', 'message': '교차 검증 및 최종 응답 포장 중...'})}\n\n"

        # 🚨 [수정 전] 수동으로 루프 돌리던 부분 
        # final_data = []
        # for rec in recommendations:
        #     final_data.append(rec.model_dump() if hasattr(rec, 'model_dump') else rec.dict())

        # 🎯 [수정 후] jsonable_encoder로 한방에 해결! (datetime 에러 완벽 해결)
        final_data = jsonable_encoder(recommendations)
        
        final_result = {
            "status": "complete",
            "data": final_data
        }
        
        # ensure_ascii=False 를 통해 한글 깨짐 방지
        yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"🚨 [Router Error] 스트리밍 추천 중 오류 발생: {e}")
        error_result = {
            "status": "error",
            "message": f"추천 처리 중 오류가 발생했습니다: {str(e)}"
        }
        yield f"data: {json.dumps(error_result, ensure_ascii=False)}\n\n"


@router.post("/stream", tags=["Recommend"])
async def stream_recommendation(
    user_req: RecommendationRequest, 
    request: Request
):
    """
    유저의 자연어 질문을 바탕으로 종목을 분석하고 결과를 SSE로 스트리밍합니다.
    """
    return StreamingResponse(
        recommend_stream_generator(request, user_req), 
        media_type="text/event-stream"
    )
