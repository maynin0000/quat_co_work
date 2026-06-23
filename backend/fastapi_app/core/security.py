import os
import jwt
import logging
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# FastAPI가 토큰을 추출할 때 사용할 스키마 (Swagger UI에도 자물쇠 아이콘 생김)
security = HTTPBearer()

# [사수의 아키텍처 포인트]
# Django의 settings.py에 있는 SECRET_KEY와 완벽하게 똑같은 문자열이어야 함!
# 반드시 준태님과 논의해서 .env 파일의 DJANGO_SECRET_KEY를 똑같이 맞출 것.
DJANGO_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "your-django-secret-key-here")
ALGORITHM = "HS256" # simplejwt의 기본 알고리즘

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> int:
    """
    프론트엔드에서 날아온 JWT(Access Token)를 해독하여 User ID를 반환하는 의존성 함수
    """
    token = credentials.credentials
    try:
        # Django가 발급한 토큰을 동일한 시크릿 키로 복호화
        payload = jwt.decode(token, DJANGO_SECRET_KEY, algorithms=[ALGORITHM])
        
        # simplejwt는 기본적으로 user_id 필드에 DB의 PK(ID)를 담아둔다.
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰에 사용자 식별자가 없습니다.",
            )
        return user_id

    except jwt.ExpiredSignatureError:
        logger.warning("⚠ 만료된 토큰 요청")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다. 다시 로그인해주세요.",
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"🚨 유효하지 않은 토큰: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 정보입니다.",
        )