import asyncio
import logging
from typing import Dict, Any, Optional
import pandas as pd
from pykrx import stock

logger = logging.getLogger(__name__)

class KrxCollector:
    def __init__(self):
        """메모리 캐싱을 통해 KRX 서버 부하 방지 및 성능 최적화"""
        self.market_cache: Dict[str, Any] = {}
        self.failed_dates: set[str] = set()

    def _get_market_data(self, date_str: str) -> Dict[str, Any]:
        """[동기] pykrx를 사용하여 특정 날짜의 시세 및 펀더멘털 데이터 로드"""
        if date_str not in self.market_cache:
            if date_str in self.failed_dates:
                return {
                    "df": pd.DataFrame(),
                    "df_fund": pd.DataFrame(),
                    "kospi": set(),
                    "kosdaq": set(),
                }
            logger.info(f"🔄 [KRX] {date_str} 기준 전체 시장 데이터 및 펀더멘털 로드...")
            try:
                df_cap = stock.get_market_cap(date_str)
                required = {"종가", "시가총액"}
                if df_cap.empty or not required.issubset(df_cap.columns):
                    raise RuntimeError("KRX 시세 응답이 비어 있거나 필수 컬럼이 없습니다.")
                kospi = set(stock.get_market_ticker_list(date_str, market="KOSPI"))
                kosdaq = set(stock.get_market_ticker_list(date_str, market="KOSDAQ"))
                df_f_kospi = stock.get_market_fundamental(date_str, market="KOSPI")
                df_f_kosdaq = stock.get_market_fundamental(date_str, market="KOSDAQ")
                df_fund = pd.concat([df_f_kospi, df_f_kosdaq])
            except Exception as exc:
                self.failed_dates.add(date_str)
                logger.warning("[KRX] %s 수집 불가, 가격 이력 데이터만 사용: %s", date_str, exc)
                return {
                    "df": pd.DataFrame(),
                    "df_fund": pd.DataFrame(),
                    "kospi": set(),
                    "kosdaq": set(),
                }
            
            # 메모리 캐시에 한 번에 저장
            self.market_cache[date_str] = {
                "df": df_cap,
                "df_fund": df_fund,
                "kospi": kospi,
                "kosdaq": kosdaq
            }
            
        return self.market_cache[date_str]

    async def fetch_ticker_data(self, date_str: str, ticker: str) -> Optional[Dict[str, Any]]:
        """
        [비동기] 특정 종목의 데이터를 normalizer.py 규격에 맞게 반환 (종가, 시총)
        """
        try:
            return await asyncio.to_thread(self._sync_fetch, date_str, ticker)
        except Exception as e:
            logger.error(f"🚨 [KRX Error] {ticker} 시세 수집 실패: {e}")
            return None

    def _sync_fetch(self, date_str: str, ticker: str) -> Optional[Dict[str, Any]]:
        cache = self._get_market_data(date_str)
        df = cache["df"]
        if df.empty:
            return None
        if ticker not in df.index:
            return None

        row = df.loc[ticker]
        market = "KOSPI" if ticker in cache["kospi"] else ("KOSDAQ" if ticker in cache["kosdaq"] else "UNKNOWN")

        return {
            "TDD_CLSPRC": int(row["종가"]),
            "MKTCAP": int(row["시가총액"]),
            "MKT_TP_NM": market
        }

    async def fetch_fundamental_data(self, date_str: str, ticker: str) -> Optional[Dict[str, Any]]:
        """
        [비동기] 특정 종목의 펀더멘털 데이터(PBR, PER, DIV) 반환
        - 협업자의 normalizer.py: normalize_krx_fundamental과 완벽 매핑
        """
        try:
            return await asyncio.to_thread(self._sync_fetch_fundamental, date_str, ticker)
        except Exception as e:
            logger.error(f"🚨 [KRX Error] {ticker} 펀더멘털 수집 실패: {e}")
            return None

    def _sync_fetch_fundamental(self, date_str: str, ticker: str) -> Optional[Dict[str, Any]]:
        cache = self._get_market_data(date_str)
        df_fund = cache["df_fund"]
        if df_fund.empty:
            return None
        if ticker not in df_fund.index:
            return None
            
        row = df_fund.loc[ticker]
        
        # PBR, PER, DIV 결측치(NaN)를 None으로 안전하게 변환
        return {
            "PBR": float(row["PBR"]) if pd.notna(row.get("PBR")) else None,
            "PER": float(row["PER"]) if pd.notna(row.get("PER")) else None,
            "DIV": float(row["DIV"]) if pd.notna(row.get("DIV")) else None,
        }
