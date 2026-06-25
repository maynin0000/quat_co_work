import asyncio
from difflib import SequenceMatcher
import json
import logging
import re
from typing import List, Tuple

from shared.schemas.financial import FinancialRawData
from shared.schemas.recommendation import Evidence, MatchResult, RecommendationResult, WhyThisStock
from shared.constants.stocks import SECTOR_STOCK_GROUPS, STOCK_PEER_GROUPS
from shared.utils.model_config import OPENAI_CHAT_MODEL

logger = logging.getLogger(__name__)


class QuantRecommender:
    GENERIC_GROUP_KEYWORDS = {"삼성", "현대", "한화", "포스코", "두산"}
    STOCK_ALIASES = {
        "005930": ["삼성전자", "삼전", "samsung전자", "samsungelectronics"],
        "000660": ["sk하이닉스", "하이닉스", "skhynix", "hynix"],
        "035420": ["네이버", "naver"],
        "033780": ["케이티앤지"],
        "373220": ["lg엔솔"],
        "207940": ["삼성바이오"],
        "005490": ["포스코홀딩스"],
        "015760": ["한전"],
        "036570": ["nc소프트"],
        "012450": ["한화에어로"],
        "047050": ["포스코인터"],
    }
    ENTITY_GROUPS = {
        "samsung": {
            "label": "삼성 계열사",
            "keywords": ["이재용", "삼성", "삼성그룹", "삼성계열", "삼성관련"],
            "tickers": ["005930", "028260", "207940", "006400", "018260"],
            "basis_date": "2026-06-25",
        },
        "sk": {
            "label": "SK 계열사",
            "keywords": ["최태원", "sk그룹", "sk계열", "sk관련"],
            "tickers": ["034730", "000660", "096770"],
            "basis_date": "2026-06-25",
        },
        "lg": {
            "label": "LG 계열사",
            "keywords": ["구광모", "lg그룹", "lg계열", "lg관련"],
            "tickers": ["003550", "066570", "051910", "373220"],
            "basis_date": "2026-06-25",
        },
        "hyundai_motor": {
            "label": "현대자동차그룹 계열사",
            "keywords": ["정의선", "현대", "현대차그룹", "현대자동차그룹", "현대관련"],
            "tickers": ["005380", "000270", "012330"],
            "basis_date": "2026-06-25",
        },
        "hanwha": {
            "label": "한화 계열사",
            "keywords": ["김승연", "한화", "한화그룹", "한화계열", "한화관련"],
            "tickers": ["012450", "042660"],
            "basis_date": "2026-06-25",
        },
        "posco": {
            "label": "포스코그룹 계열사",
            "keywords": ["포스코", "posco그룹", "포스코그룹", "포스코계열", "포스코관련"],
            "tickers": ["005490", "003670", "047050"],
            "basis_date": "2026-06-25",
        },
        "hd_hyundai": {
            "label": "HD현대 계열사",
            "keywords": ["hd현대그룹", "hd현대계열", "hd현대관련"],
            "tickers": ["267250", "329180", "009540"],
            "basis_date": "2026-06-25",
        },
        "doosan": {
            "label": "두산그룹 계열사",
            "keywords": ["두산", "두산그룹", "두산계열", "두산관련"],
            "tickers": ["034020", "241560"],
            "basis_date": "2026-06-25",
        },
    }

    FACTOR_SYNONYMS = {
        "value": ["pbr", "per", "ev/ebitda", "psr", "저pbr", "저평가", "value", "가치주", "가치"],
        "quality": ["roe", "roa", "영업이익률", "수익성", "profitability", "quality", "퀄리티", "우량주"],
        "growth": ["growth", "성장", "성장주", "매출성장", "이익성장", "고성장"],
        "dividend": ["dividend", "\ubc30\ub2f9", "\ubc30\ub2f9\uc218\uc775\ub960", "\uace0\ubc30\ub2f9", "income"],
        "momentum": ["momentum", "\ubaa8\uba58\ud140", "\ucd94\uc138", "\uc0c1\uc2b9\uc138", "sentiment", "\uc2ec\ub9ac"],
        "defensive": ["debt", "부채", "안정", "안전", "재무건전성", "volatility", "변동성", "방어", "risk", "리스크"],
        "size": ["size", "\ub300\ud615\uc8fc", "\uc18c\ud615\uc8fc", "liquidity", "\uc720\ub3d9\uc131", "\uc2dc\uac00\ucd1d\uc561"],
        "governance": ["governance", "esg", "\uc9c0\ubc30\uad6c\uc870", "\uc9c0\ubc30"],
    }

    FACTOR_RULES = {
        "value": [
            ("pbr", "PBR", "< 1.2", lambda v: 0 < v < 1.2, 25),
            ("per", "PER", "< 15", lambda v: 0 < v < 15, 20),
            ("ev_ebitda", "EV/EBITDA", "< 10", lambda v: 0 < v < 10, 15),
            ("psr", "PSR", "< 2", lambda v: 0 < v < 2, 10),
            ("fcf_yield", "FCF 수익률", "> 5%", lambda v: v > 5, 15),
            ("roe", "ROE", "> 8%", lambda v: v > 8, 10),
            ("op_margin", "영업이익률", "> 5%", lambda v: v > 5, 10),
            ("debt_ratio", "부채비율", "< 150%", lambda v: v < 150, 10),
        ],
        "quality": [
            ("roe", "ROE", "> 10%", lambda v: v > 10, 25),
            ("roa", "ROA", "> 5%", lambda v: v > 5, 15),
            ("op_margin", "영업이익률", "> 8%", lambda v: v > 8, 20),
            ("debt_ratio", "부채비율", "< 100%", lambda v: v < 100, 20),
            ("current_ratio", "유동비율", "> 100%", lambda v: v > 100, 20),
            ("operating_cash_flow", "영업현금흐름", "> 0", lambda v: v > 0, 10),
        ],
        "growth": [
            ("revenue_growth", "매출성장률", "> 10%", lambda v: v > 10, 25),
            ("profit_growth", "순이익성장률", "> 10%", lambda v: v > 10, 25),
            ("op_growth", "영업이익성장률", "> 10%", lambda v: v > 10, 20),
            ("op_margin", "영업이익률", "> 5%", lambda v: v > 5, 15),
            ("operating_cash_flow", "영업현금흐름", "> 0", lambda v: v > 0, 10),
            ("momentum_1y", "12개월 모멘텀", "> 0%", lambda v: v > 0, 15),
        ],
        "momentum": [
            ("momentum_1y", "12개월 모멘텀", "> 0%", lambda v: v > 0, 35),
            ("momentum_6m", "6개월 모멘텀", "> 0%", lambda v: v > 0, 25),
            ("momentum_3m", "3개월 모멘텀", "> 0%", lambda v: v > 0, 20),
            ("momentum_1m", "1개월 모멘텀", "> -5%", lambda v: v > -5, 5),
            ("volatility", "변동성", "< 40%", lambda v: v < 40, 15),
        ],
        "dividend": [
            ("dividend_yield", "배당수익률", "> 3%", lambda v: v > 3, 35),
            ("dividend_growth", "배당성장률", ">= 0%", lambda v: v >= 0, 15),
            ("roe", "ROE", "> 8%", lambda v: v > 8, 15),
            ("debt_ratio", "부채비율", "< 150%", lambda v: v < 150, 20),
            ("op_margin", "영업이익률", "> 5%", lambda v: v > 5, 15),
        ],
        "defensive": [
            ("debt_ratio", "부채비율", "< 100%", lambda v: v < 100, 25),
            ("current_ratio", "유동비율", "> 100%", lambda v: v > 100, 20),
            ("volatility", "변동성", "< 30%", lambda v: v < 30, 25),
            ("roe", "ROE", "> 5%", lambda v: v > 5, 15),
            ("dividend_yield", "배당수익률", "> 2%", lambda v: v > 2, 15),
            ("operating_cash_flow", "영업현금흐름", "> 0", lambda v: v > 0, 10),
        ],
    }

    def __init__(self, vector_store, financial_repo, llm_client):
        self.vector_store = vector_store
        self.financial_repo = financial_repo
        self.llm_client = llm_client

    def _extract_canonical_factors(self, query: str) -> List[str]:
        query_lower = query.lower()
        return [
            canonical
            for canonical, synonyms in self.FACTOR_SYNONYMS.items()
            if any(syn in query_lower for syn in synonyms)
        ]

    def _is_sector_query(self, query: str) -> bool:
        query_lower = query.lower()
        sector_terms = [
            keyword
            for group in SECTOR_STOCK_GROUPS.values()
            for keyword in group["keywords"]
        ]
        return any(term.lower() in query_lower for term in sector_terms)

    @staticmethod
    def _normalize_stock_term(value: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]", "", value.lower())

    async def search_named_stocks(
        self,
        user_query: str,
        top_n: int = 5,
    ) -> List[RecommendationResult]:
        """종목명·종목코드가 명시된 요청은 RAG 검색보다 우선해서 반환한다."""
        normalized_query = self._normalize_stock_term(user_query)
        if not normalized_query:
            return []

        stocks = await self.financial_repo.get_all_stocks()
        stocks_by_ticker = {stock.ticker: stock for stock in stocks}
        positioned_matches = []
        for stock in stocks:
            candidates = [stock.name, stock.ticker, *self.STOCK_ALIASES.get(stock.ticker, [])]
            matches = []
            for candidate in candidates:
                normalized_candidate = self._normalize_stock_term(candidate)
                if not normalized_candidate or normalized_candidate not in normalized_query:
                    continue
                position = normalized_query.find(normalized_candidate)
                exact = normalized_query == normalized_candidate
                matches.append((0 if exact else 1, position, -len(normalized_candidate)))
            if matches:
                positioned_matches.append((*min(matches), stock))

        if any(match[0] == 0 for match in positioned_matches):
            positioned_matches = [match for match in positioned_matches if match[0] == 0]
        else:
            if self._is_sector_query(user_query):
                sector_results = self._search_sector_groups(
                    normalized_query,
                    stocks_by_ticker,
                    top_n,
                )
                if sector_results:
                    return sector_results
            entity_results = self._search_entity_groups(
                normalized_query,
                stocks_by_ticker,
                top_n,
            )
            if entity_results:
                return entity_results
            typo_matches = self._search_typo_stocks(user_query, stocks) if not positioned_matches else []
            if typo_matches:
                positioned_matches = [
                    (2, index, -len(stock.name), stock)
                    for index, stock in enumerate(typo_matches)
                ]

        positioned_matches.sort(key=lambda item: item[:3])
        matched_stocks = [stock for _, _, _, stock in positioned_matches[:top_n]]
        comparison_requested = (
            len(matched_stocks) >= 2
            and any(word in user_query.lower() for word in ["비교", "vs", "대비", "중에", "중에서"])
        )
        if comparison_requested:
            return [
                self._format_comparison_stock(stock, matched_stocks)
                for stock in matched_stocks
            ]

        query_factors = self._extract_canonical_factors(user_query)
        if len(matched_stocks) == 1 and query_factors:
            return [self._format_condition_stock(matched_stocks[0], query_factors)]

        direct_results = [
            self._format_named_stock(stock)
            for stock in matched_stocks
        ]
        if len(direct_results) == 1:
            target = positioned_matches[0][3]
            similar_stocks = self._find_similar_stocks(
                target,
                stocks_by_ticker,
                limit=min(3, max(top_n - 1, 0)),
            )
            direct_results.extend(
                self._format_similar_stock(stock, target)
                for stock in similar_stocks
            )
        return direct_results

    def _format_comparison_stock(
        self,
        stock: FinancialRawData,
        compared_stocks: List[FinancialRawData],
    ) -> RecommendationResult:
        result = self._format_named_stock(stock)
        result.matched_strategies = ["종목 비교"]
        result.why_this_stock = WhyThisStock(
            paper_basis="사용자가 여러 종목의 비교를 요청했습니다.",
            current_status=self._stock_status_text(stock),
            match_summary=f"{len(compared_stocks)}개 종목을 동일한 지표 기준으로 비교합니다.",
        )
        result.simple_summary = f"비교 대상: {stock.name}({stock.ticker})"
        return result

    def _format_condition_stock(
        self,
        stock: FinancialRawData,
        factors: List[str],
    ) -> RecommendationResult:
        active = [factor for factor in factors if factor in self.FACTOR_RULES]
        match_results = []
        passed = 0
        for factor in active:
            for field, label, condition, predicate, _ in self.FACTOR_RULES[factor]:
                value = getattr(stock, field)
                if value is None:
                    continue
                is_match = bool(predicate(float(value)))
                passed += int(is_match)
                match_results.append(MatchResult(
                    factor=label,
                    paper_condition=condition,
                    stock_value=float(value),
                    is_match=is_match,
                    gap=0.0,
                ))
        coverage = len(match_results)
        result = self._format_named_stock(stock)
        result.matched_strategies = ["종목 조건 분석"]
        result.match_results = match_results
        result.recommendation_score = (
            round(passed / coverage * 100, 2) if coverage else 0.0
        )
        result.why_this_stock = WhyThisStock(
            paper_basis=f"검색어에서 {', '.join(active)} 조건을 인식했습니다.",
            current_status=self._stock_status_text(stock),
            match_summary=(
                f"확인 가능한 조건 {coverage}개 중 {passed}개를 충족했습니다."
                if coverage else "해당 조건을 판단할 재무 데이터가 부족합니다."
            ),
        )
        result.simple_summary = f"{stock.name}의 요청 조건 분석 결과입니다."
        return result

    @staticmethod
    def _stock_status_text(stock: FinancialRawData) -> str:
        values = []
        for field, label in (
            ("pbr", "PBR"), ("per", "PER"), ("roe", "ROE"),
            ("dividend_yield", "배당"), ("momentum_1y", "12개월 모멘텀"),
            ("volatility", "변동성"),
        ):
            value = getattr(stock, field)
            if value is not None:
                values.append(f"{label} {value:g}")
        return ", ".join(values) or "표시 가능한 지표가 제한적입니다."

    @staticmethod
    def _find_similar_stocks(
        target: FinancialRawData,
        stocks_by_ticker: dict[str, FinancialRawData],
        limit: int,
    ) -> List[FinancialRawData]:
        candidates = []
        for group in STOCK_PEER_GROUPS:
            if target.ticker not in group:
                continue
            for ticker in group:
                if ticker != target.ticker and ticker not in candidates:
                    candidates.append(ticker)

        def distance(ticker: str) -> tuple[float, int]:
            peer = stocks_by_ticker[ticker]
            fields = ("pbr", "per", "roe", "momentum_1y", "market_cap")
            differences = []
            for field in fields:
                left = getattr(target, field)
                right = getattr(peer, field)
                if left is None or right is None:
                    continue
                scale = max(abs(float(left)), abs(float(right)), 1.0)
                differences.append(abs(float(left) - float(right)) / scale)
            return (
                sum(differences) / len(differences) if differences else 1.0,
                candidates.index(ticker),
            )

        available = [ticker for ticker in candidates if ticker in stocks_by_ticker]
        available.sort(key=distance)
        return [stocks_by_ticker[ticker] for ticker in available[:limit]]

    def _format_similar_stock(
        self,
        stock: FinancialRawData,
        target: FinancialRawData,
    ) -> RecommendationResult:
        result = self._format_named_stock(stock)
        result.recommendation_score = 0.0
        result.confidence_score = min(result.confidence_score, 75.0)
        result.matched_strategies = ["유사 종목 추천"]
        comparable_fields = []
        for field, label in (
            ("market_cap", "시가총액"),
            ("pbr", "PBR"),
            ("per", "PER"),
            ("momentum_1y", "12개월 모멘텀"),
            ("volatility", "변동성"),
        ):
            if getattr(target, field) is not None and getattr(stock, field) is not None:
                comparable_fields.append(label)
        basis = "·".join(comparable_fields[:3]) or "업종·사업군"
        result.why_this_stock = WhyThisStock(
            paper_basis=f"{target.name}과 같은 업종·사업군 후보로 분류했습니다.",
            current_status=(
                f"{target.name} 검색 결과와 함께 비교할 수 있는 유사 종목입니다."
            ),
            match_summary=f"같은 사업군을 우선하고 {basis} 유사도를 보조 기준으로 사용했습니다.",
        )
        result.simple_summary = f"{target.name}과 비교해 볼 유사 종목: {stock.name}({stock.ticker})"
        result.risk_factors = ["유사 업종 분류는 투자 성과의 유사성을 보장하지 않습니다."]
        return result

    def _search_sector_groups(
        self,
        normalized_query: str,
        stocks_by_ticker: dict[str, FinancialRawData],
        top_n: int,
    ) -> List[RecommendationResult]:
        matched_groups = []
        for group in SECTOR_STOCK_GROUPS.values():
            normalized_keywords = [
                self._normalize_stock_term(keyword)
                for keyword in group["keywords"]
            ]
            matched_lengths = [
                len(keyword)
                for keyword in normalized_keywords
                if keyword and keyword in normalized_query
            ]
            if matched_lengths:
                matched_groups.append((max(matched_lengths), group))

        if not matched_groups:
            return []

        _, group = max(matched_groups, key=lambda item: item[0])
        results = []
        for ticker in group["tickers"][:top_n]:
            stock = stocks_by_ticker.get(ticker)
            if stock is not None:
                results.append(self._format_sector_stock(stock, group))
        return results

    def _format_sector_stock(
        self,
        stock: FinancialRawData,
        group: dict,
    ) -> RecommendationResult:
        return RecommendationResult(
            ticker=stock.ticker,
            name=stock.name,
            recommendation_score=0.0,
            confidence_score=75.0,
            matched_strategies=[f"{group['label']} 연관 검색"],
            why_this_stock=WhyThisStock(
                paper_basis=(
                    f"검색어를 {group['label']} 업종 질의로 해석했습니다. "
                    f"업종 기준일은 {group['basis_date']}입니다."
                ),
                current_status=f"{group['label']} 관련 종목으로 분류된 검색 결과입니다.",
                match_summary=(
                    f"{group['label']} 업종에 속한 종목만 우선 추렸습니다. "
                    "유사 업종끼리 묶어 보여주는 결과입니다."
                ),
            ),
            match_results=[],
            risk_factors=[
                "업종 연관 검색 결과이며, 개별 종목의 투자 추천은 아닙니다.",
                "업종 대표주 위주로 보여주므로 세부 소재/장비주는 별도 탐색이 필요합니다.",
            ],
            simple_summary=f"{stock.name}({stock.ticker}) — {group['label']} 업종 연관 검색 결과",
            evidence=[
                Evidence(
                    claim=f"{group['label']} 업종 카탈로그에 포함되어 있습니다.",
                    source=f"데모 업종 매핑 · 기준일 {group['basis_date']}",
                )
            ],
            data_date=stock.data_date,
            data_sources=self._data_sources(stock),
        )

    def _search_typo_stocks(
        self,
        user_query: str,
        stocks: List[FinancialRawData],
    ) -> List[FinancialRawData]:
        """3자 이상 종목명에 한해 제한적으로 오타·접두 검색을 허용한다."""
        normalized_query = self._normalize_stock_term(user_query)
        query_terms = {
            normalized_query,
            *(
                self._normalize_stock_term(term)
                for term in re.findall(r"[0-9A-Za-z가-힣]+", user_query)
            ),
        }
        query_terms = {
            term for term in query_terms
            if len(term) >= 3 and term not in {"분석", "검색", "주가", "종목", "추천"}
        }
        if not query_terms:
            return []

        scored = []
        for stock in stocks:
            candidates = [stock.name, *self.STOCK_ALIASES.get(stock.ticker, [])]
            best_score = 0.0
            for candidate in candidates:
                normalized_candidate = self._normalize_stock_term(candidate)
                if len(normalized_candidate) < 3:
                    continue
                for term in query_terms:
                    if normalized_candidate.startswith(term) or term.startswith(normalized_candidate):
                        prefix_ratio = min(len(term), len(normalized_candidate)) / max(
                            len(term), len(normalized_candidate)
                        )
                        score = 0.9 + 0.1 * prefix_ratio
                    elif self._edit_distance(term, normalized_candidate) <= 1:
                        score = 0.8
                    else:
                        score = SequenceMatcher(None, term, normalized_candidate).ratio()
                    best_score = max(best_score, score)
            if best_score >= 0.72:
                scored.append((best_score, len(stock.name), stock))

        scored.sort(key=lambda item: (-item[0], -item[1]))
        return [stock for _, _, stock in scored[:1]]

    @staticmethod
    def _edit_distance(left: str, right: str) -> int:
        previous = list(range(len(right) + 1))
        for left_index, left_char in enumerate(left, 1):
            current = [left_index]
            for right_index, right_char in enumerate(right, 1):
                current.append(min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                ))
            previous = current
        return previous[-1]

    def _search_entity_groups(
        self,
        normalized_query: str,
        stocks_by_ticker: dict[str, FinancialRawData],
        top_n: int,
    ) -> List[RecommendationResult]:
        matched_groups = []
        for group in self.ENTITY_GROUPS.values():
            normalized_keywords = [
                self._normalize_stock_term(keyword)
                for keyword in group["keywords"]
            ]
            matched_lengths = [
                len(keyword)
                for keyword in normalized_keywords
                if keyword
                and (
                    normalized_query == keyword
                    if keyword in {
                        self._normalize_stock_term(item)
                        for item in self.GENERIC_GROUP_KEYWORDS
                    }
                    else keyword in normalized_query
                )
            ]
            if matched_lengths:
                matched_groups.append((max(matched_lengths), group))

        if not matched_groups:
            return []
        _, group = max(matched_groups, key=lambda item: item[0])
        results = []
        for ticker in group["tickers"][:top_n]:
            stock = stocks_by_ticker.get(ticker)
            if stock is not None:
                results.append(self._format_entity_stock(stock, group))
        return results

    def _format_entity_stock(
        self,
        stock: FinancialRawData,
        group: dict,
    ) -> RecommendationResult:
        return RecommendationResult(
            ticker=stock.ticker,
            name=stock.name,
            recommendation_score=0.0,
            confidence_score=70.0,
            matched_strategies=["인물·기업집단 연관 검색"],
            why_this_stock=WhyThisStock(
                paper_basis=(
                    f"검색어를 {group['label']} 연관 키워드로 해석했습니다. "
                    f"관계 기준일은 {group['basis_date']}입니다."
                ),
                current_status=f"{group['label']} 연관 종목으로 분류된 검색 결과입니다.",
                match_summary="인물·기업집단 연관성은 투자 매력도나 매수 의견을 의미하지 않습니다.",
            ),
            match_results=[],
            risk_factors=[
                "기업집단 연관 검색 결과이며 투자 추천 순위가 아닙니다.",
                "계열 관계와 지배구조는 변경될 수 있습니다.",
            ],
            simple_summary=f"{stock.name}({stock.ticker}) — {group['label']} 연관 검색 결과",
            evidence=[
                Evidence(
                    claim=f"{group['label']} 연관 종목 카탈로그에 포함되어 있습니다.",
                    source=f"데모 기업집단 매핑 · 기준일 {group['basis_date']}",
                )
            ],
            data_date=stock.data_date,
            data_sources=self._data_sources(stock),
        )

    def _format_named_stock(self, stock: FinancialRawData) -> RecommendationResult:
        fields = [
            ("PBR", "참고 지표", stock.pbr, stock.pbr is not None and 0 < stock.pbr < 1.2),
            ("PER", "참고 지표", stock.per, stock.per is not None and 0 < stock.per < 15),
            ("ROE", "참고 지표", stock.roe, stock.roe is not None and stock.roe > 10),
            (
                "12개월 모멘텀",
                "참고 지표",
                stock.momentum_1y,
                stock.momentum_1y is not None and stock.momentum_1y > 0,
            ),
        ]
        match_results = [
            MatchResult(
                factor=label,
                paper_condition=condition,
                stock_value=float(value),
                is_match=bool(is_match),
                gap=0.0,
            )
            for label, condition, value, is_match in fields
            if value is not None
        ]
        current_status = ", ".join(
            f"{result.factor} {result.stock_value:g}"
            for result in match_results
        ) or "표시 가능한 재무 지표가 제한적입니다."

        return RecommendationResult(
            ticker=stock.ticker,
            name=stock.name,
            recommendation_score=0.0,
            confidence_score=min(95.0, max(55.0, stock.data_completeness)),
            matched_strategies=["직접 종목명 검색"],
            why_this_stock=WhyThisStock(
                paper_basis="사용자가 종목명 또는 종목코드를 직접 지정했습니다.",
                current_status=current_status,
                match_summary="검색어와 종목명이 일치하여 우선 표시한 결과입니다.",
            ),
            match_results=match_results,
            risk_factors=[
                "직접 검색 결과이며 매수 추천 순위가 아닙니다.",
                *(
                    ["현재 재무 필드가 제한적이므로 가격·모멘텀 중심으로 표시합니다."]
                    if stock.data_completeness < 50 else []
                ),
            ],
            simple_summary=f"{stock.name}({stock.ticker}) 직접 검색 결과입니다.",
            evidence=[
                Evidence(
                    claim="사용자 검색어와 종목명 또는 별칭이 일치합니다.",
                    source="종목 마스터 데이터",
                )
            ],
            data_date=stock.data_date,
            data_sources=self._data_sources(stock),
        )

    async def generate_recommendation(
        self,
        user_query: str,
        query_embedding: List[float],
        top_n: int = 5,
    ) -> List[RecommendationResult]:
        logger.info("[Recommender] starting recommendation for query: %s", user_query)

        direct_results = await self.search_named_stocks(user_query, top_n)
        if direct_results:
            logger.info("[Recommender] direct stock-name matches: %s", len(direct_results))
            return direct_results

        canonical_factors = self._extract_canonical_factors(user_query)
        logger.info("[Reranker] extracted canonical factors: %s", canonical_factors)

        search_results = await self.vector_store.search_papers_async(
            query_embedding=query_embedding,
            n_results=10,
            min_completeness=80.0,
        )
        raw_docs = search_results.get("documents", [[]])[0]
        if not raw_docs:
            logger.warning("[Recommender] no related paper strategies found")
            return []

        reranked_docs = []
        for idx, doc in enumerate(raw_docs):
            doc_lower = doc.lower()
            overlap_score = 0
            for factor in canonical_factors:
                if any(syn in doc_lower for syn in self.FACTOR_SYNONYMS[factor]):
                    overlap_score += 1
            reranked_docs.append((doc, overlap_score, idx))

        reranked_docs.sort(key=lambda item: (-item[1], item[2]))

        if canonical_factors and reranked_docs and reranked_docs[0][1] == 0:
            try:
                collection = getattr(self.vector_store, "paper_collection", None)
                if collection is not None:
                    all_results = await asyncio.to_thread(
                        collection.get,
                        where={"completeness": {"$gte": 80.0}},
                        include=["documents"],
                    )
                    all_docs = all_results.get("documents", []) if all_results else []
                    lexical_docs = []
                    for idx, doc in enumerate(all_docs):
                        doc_lower = doc.lower()
                        overlap_score = 0
                        for factor in canonical_factors:
                            if any(syn in doc_lower for syn in self.FACTOR_SYNONYMS[factor]):
                                overlap_score += 1
                        lexical_docs.append((doc, overlap_score, idx))

                    lexical_docs.sort(key=lambda item: (-item[1], item[2]))
                    if lexical_docs and lexical_docs[0][1] > 0:
                        reranked_docs = lexical_docs
                        logger.info(
                            "[Reranking] lexical fallback selected overlap=%s",
                            lexical_docs[0][1],
                        )
            except Exception as e:
                logger.warning("[Reranking] lexical fallback failed: %s", e)

        retrieved_strategies = [doc for doc, _, _ in reranked_docs[:3]]
        logger.info(
            "[Reranking] selected top strategy overlap=%s: %s...",
            reranked_docs[0][1],
            retrieved_strategies[0][:100],
        )

        all_stocks: List[FinancialRawData] = await self.financial_repo.get_all_stocks()
        matched_stocks = await self._match_strategies_to_stocks(
            retrieved_strategies,
            all_stocks,
            canonical_factors,
            user_query,
        )
        top_stocks = matched_stocks[:top_n]
        if not top_stocks:
            return []

        return await self._batch_format_to_schema(top_stocks, retrieved_strategies)

    async def _match_strategies_to_stocks(
        self,
        strategies: List[str],
        stocks: List[FinancialRawData],
        query_factors: List[str],
        user_query: str,
    ):
        combined_strategy_text = " ".join(strategies).lower()
        active_factors = [
            factor for factor in query_factors
            if factor in self.FACTOR_RULES
        ]
        if not active_factors:
            active_factors = [
                factor for factor, synonyms in self.FACTOR_SYNONYMS.items()
                if factor in self.FACTOR_RULES
                and any(syn in combined_strategy_text for syn in synonyms)
            ]
        if not active_factors:
            active_factors = ["value", "quality"]

        requested_tier = self._extract_size_tier(user_query)
        scored_stocks = []

        for stock in stocks:
            if requested_tier and stock.market_cap_tier != requested_tier:
                continue

            earned_weight = 0.0
            available_weight = 0.0
            total_weight = 0.0
            available_count = 0
            match_details = []
            match_results = []

            for factor in active_factors:
                rules = self.FACTOR_RULES[factor]
                total_weight += sum(rule[4] for rule in rules)
                for field, label, condition, predicate, weight in rules:
                    value = getattr(stock, field)
                    if value is None:
                        continue
                    available_count += 1
                    available_weight += weight
                    passed = bool(predicate(float(value)))
                    earned_weight += weight * self._criterion_strength(
                        field,
                        float(value),
                    )
                    if passed:
                        match_details.append(f"{label} {value:g}")
                    match_results.append(MatchResult(
                        factor=label,
                        paper_condition=condition,
                        stock_value=float(value),
                        is_match=passed,
                        gap=0.0,
                    ))

            if "value" in active_factors:
                relative_strength = self._relative_value_strength(stock, stocks)
                if relative_strength is not None:
                    total_weight += 15
                    available_weight += 15
                    available_count += 1
                    earned_weight += 15 * relative_strength
                    relative_score = round(relative_strength * 100, 2)
                    relative_pass = relative_strength >= 0.6
                    if relative_pass:
                        match_details.append(f"동종군 상대가치 {relative_score:g}점")
                    match_results.append(MatchResult(
                        factor="동종군 상대가치",
                        paper_condition="상위 40%",
                        stock_value=relative_score,
                        is_match=relative_pass,
                        gap=0.0,
                    ))

            if available_count < 2 or available_weight == 0:
                continue

            factor_score = earned_weight / available_weight * 100
            coverage = min(1.0, available_weight / max(total_weight, 1))
            score = round(factor_score * (0.7 + 0.3 * coverage), 2)
            if score >= 35:
                scored_stocks.append(
                    (stock, score, match_details, match_results, round(coverage * 100, 1))
                )

        scored_stocks.sort(key=lambda x: x[1], reverse=True)
        return scored_stocks

    @staticmethod
    def _criterion_strength(field: str, value: float) -> float:
        """임계값 통과 여부뿐 아니라 지표의 강도를 0~1 연속 점수로 환산한다."""
        lower_is_better = {
            "pbr": (2.0, 1.5),
            "per": (25.0, 20.0),
            "ev_ebitda": (15.0, 12.0),
            "psr": (3.0, 2.5),
            "debt_ratio": (200.0, 180.0),
            "volatility": (50.0, 40.0),
        }
        higher_is_better = {
            "roe": (0.0, 20.0),
            "roa": (0.0, 10.0),
            "op_margin": (0.0, 20.0),
            "current_ratio": (50.0, 150.0),
            "revenue_growth": (-5.0, 35.0),
            "profit_growth": (-5.0, 35.0),
            "op_growth": (-5.0, 35.0),
            "momentum_1y": (-20.0, 50.0),
            "momentum_6m": (-15.0, 35.0),
            "momentum_3m": (-10.0, 25.0),
            "momentum_1m": (-10.0, 20.0),
            "dividend_yield": (0.0, 7.0),
            "dividend_growth": (-5.0, 15.0),
            "fcf_yield": (-5.0, 20.0),
        }
        if field in lower_is_better:
            ceiling, span = lower_is_better[field]
            return max(0.0, min(1.0, (ceiling - value) / span))
        if field in higher_is_better:
            floor, span = higher_is_better[field]
            return max(0.0, min(1.0, (value - floor) / span))
        if field in {"operating_cash_flow", "free_cash_flow"}:
            return 1.0 if value > 0 else 0.0
        return 1.0

    @staticmethod
    def _relative_value_strength(stock: FinancialRawData, stocks: List[FinancialRawData]):
        peers = [
            peer for peer in stocks
            if peer.ticker != stock.ticker
            and (
                (stock.sector and peer.sector == stock.sector)
                or (not stock.sector and peer.market_cap_tier == stock.market_cap_tier)
            )
        ]
        if len(peers) < 3:
            peers = [peer for peer in stocks if peer.ticker != stock.ticker]

        percentiles = []
        for field in ("pbr", "per", "ev_ebitda", "psr"):
            value = getattr(stock, field)
            peer_values = [
                getattr(peer, field)
                for peer in peers
                if getattr(peer, field) is not None and getattr(peer, field) > 0
            ]
            if value is None or value <= 0 or len(peer_values) < 3:
                continue
            cheaper_count = sum(peer_value >= value for peer_value in peer_values)
            percentiles.append(cheaper_count / len(peer_values))
        if not percentiles:
            return None
        return sum(percentiles) / len(percentiles)

    @staticmethod
    def _extract_size_tier(query: str):
        query_lower = query.lower()
        if any(word in query_lower for word in ["소형주", "소형", "small cap", "small-cap"]):
            return "small"
        if any(word in query_lower for word in ["중형주", "중형", "mid cap", "mid-cap"]):
            return "mid"
        if any(word in query_lower for word in ["대형주", "대형", "large cap", "large-cap"]):
            return "large"
        return None

    async def _batch_format_to_schema(
        self,
        top_stocks: List[Tuple],
        strategies: List[str],
    ) -> List[RecommendationResult]:
        stock_summaries = []
        for stock, score, match_details, _, coverage in top_stocks:
            stock_summaries.append({
                "ticker": stock.ticker,
                "name": stock.name,
                "quant_score": score,
                "matched_factors": match_details,
                "data_coverage": coverage,
            })

        system_prompt = f"""
Return JSON only. Analyze the paper strategy and matched stocks.

Paper strategy:
{strategies[0][:500]}

Matched stocks:
{json.dumps(stock_summaries, ensure_ascii=False)}

Schema:
{{
  "recommendations": [
    {{
      "ticker": "stock ticker",
      "confidence_score": 85.5,
      "why_this_stock": {{
        "paper_basis": "one sentence about the paper basis",
        "current_status": "one sentence about the stock's current factor status",
        "match_summary": "one sentence explaining the match"
      }},
      "simple_summary": "short investor-friendly recommendation summary",
      "risk_factors": ["risk 1", "risk 2"],
      "evidence": [
        {{
          "source": "paper strategy or matched financial factor",
          "claim": "concrete supporting claim"
        }}
      ]
    }}
  ]
}}
"""

        llm_responses = {}
        try:
            response = await self.llm_client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.3,
            )
            parsed_data = json.loads(response.choices[0].message.content)
            for item in parsed_data.get("recommendations", []):
                if "ticker" in item:
                    llm_responses[item["ticker"]] = item
        except Exception as e:
            logger.error("[Recommender Error] LLM explanation failed; using fallback: %s", e)

        final_results = []
        for stock, score, match_details, match_results, coverage in top_stocks:
            llm_info = llm_responses.get(stock.ticker, {})
            raw_why = llm_info.get("why_this_stock", {})
            if not isinstance(raw_why, dict):
                raw_why = {}

            why_obj = WhyThisStock(
                paper_basis=raw_why.get("paper_basis", "Retrieved paper strategy basis"),
                current_status=raw_why.get("current_status", f"Matched factors: {', '.join(match_details)}"),
                match_summary=raw_why.get("match_summary", raw_why.get("reason", "Matched by quantitative financial rules")),
            )

            raw_evidence = llm_info.get("evidence", [])
            evidence_list = []
            if isinstance(raw_evidence, list):
                for ev in raw_evidence:
                    if not isinstance(ev, dict):
                        continue
                    claim = ev.get("claim") or ev.get("content")
                    source = ev.get("source") or "RAG strategy"
                    if claim:
                        evidence_list.append(Evidence(claim=str(claim), source=str(source)))

            result = RecommendationResult(
                ticker=stock.ticker,
                name=stock.name,
                recommendation_score=score,
                confidence_score=float(llm_info.get(
                    "confidence_score",
                    min(99.0, score * 0.8 + coverage * 0.2),
                )),
                matched_strategies=[strategies[0][:50]],
                why_this_stock=why_obj,
                match_results=match_results,
                risk_factors=llm_info.get("risk_factors", ["Market volatility risk"]),
                simple_summary=llm_info.get("simple_summary", f"{stock.name}: quant-matched candidate"),
                evidence=evidence_list,
                data_date=stock.data_date,
                data_sources=self._data_sources(stock),
            )
            final_results.append(result)

        return final_results

    @staticmethod
    def _data_sources(stock: FinancialRawData) -> List[str]:
        sources = []
        if stock.price is not None or stock.momentum_1y is not None:
            sources.append("가격·모멘텀: FinanceDataReader 실수집")
        if any(getattr(stock, field) is not None for field in ("pbr", "per", "roe", "dividend_yield")):
            sources.append("재무지표: KRX 실수집 또는 데모 보완")
        return sources or ["종목 기본정보: 공통 카탈로그"]
