import asyncio
import json
import logging
from typing import List, Tuple

from shared.schemas.financial import FinancialRawData
from shared.schemas.recommendation import Evidence, MatchResult, RecommendationResult, WhyThisStock
from shared.utils.model_config import OPENAI_CHAT_MODEL

logger = logging.getLogger(__name__)


class QuantRecommender:
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

    async def generate_recommendation(
        self,
        user_query: str,
        query_embedding: List[float],
        top_n: int = 5,
    ) -> List[RecommendationResult]:
        logger.info("[Recommender] starting recommendation for query: %s", user_query)

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
            )
            final_results.append(result)

        return final_results
