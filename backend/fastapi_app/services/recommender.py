import asyncio
import json
import logging
from typing import List, Tuple

from shared.schemas.financial import FinancialRawData
from shared.schemas.recommendation import Evidence, MatchResult, RecommendationResult, WhyThisStock

logger = logging.getLogger(__name__)


class QuantRecommender:
    FACTOR_SYNONYMS = {
        "pbr": ["pbr", "\uc800pbr", "\uc800 pbr", "\uc800\ud3c9\uac00", "value", "\uac00\uce58\uc8fc"],
        "roe": ["roe", "\uace0roe", "\uace0 roe", "\uc218\uc775\uc131", "profitability", "quality"],
        "dividend": ["dividend", "\ubc30\ub2f9", "\ubc30\ub2f9\uc218\uc775\ub960", "\uace0\ubc30\ub2f9", "income"],
        "debt": ["debt", "\ubd80\ucc44", "\ubd80\ucc44\ube44\uc728", "\uc548\uc815\uc131", "\uc7ac\ubb34\uac74\uc804\uc131"],
        "volatility": ["volatility", "\ubcc0\ub3d9\uc131", "risk", "\ub9ac\uc2a4\ud06c"],
        "momentum": ["momentum", "\ubaa8\uba58\ud140", "\ucd94\uc138", "\uc0c1\uc2b9\uc138", "sentiment", "\uc2ec\ub9ac"],
        "size": ["size", "\ub300\ud615\uc8fc", "\uc18c\ud615\uc8fc", "liquidity", "\uc720\ub3d9\uc131", "\uc2dc\uac00\ucd1d\uc561"],
        "industry": ["industry", "\uc0b0\uc5c5", "\uc0b0\uc5c5\uc694\uc778", "growth", "\uc131\uc7a5\uc131"],
        "governance": ["governance", "esg", "\uc9c0\ubc30\uad6c\uc870", "\uc9c0\ubc30"],
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
        matched_stocks = await self._match_strategies_to_stocks(retrieved_strategies, all_stocks)
        top_stocks = matched_stocks[:top_n]
        if not top_stocks:
            return []

        return await self._batch_format_to_schema(top_stocks, retrieved_strategies)

    async def _match_strategies_to_stocks(
        self,
        strategies: List[str],
        stocks: List[FinancialRawData],
    ):
        combined_strategy_text = " ".join(strategies).lower()
        scored_stocks = []

        for stock in stocks:
            score = 0.0
            match_details = []
            match_results = []

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["pbr"]):
                if stock.pbr is not None and 0 < stock.pbr < 1.0:
                    score += 20
                    match_details.append(f"low PBR ({stock.pbr})")
                    match_results.append(MatchResult(
                        factor="PBR",
                        paper_condition="< 1.0",
                        stock_value=float(stock.pbr),
                        is_match=True,
                        gap=round(float(stock.pbr) - 1.0, 4),
                    ))
                if stock.per is not None and 0 < stock.per < 15.0:
                    score += 10
                    match_details.append(f"low PER ({stock.per})")

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["roe"]):
                if stock.roe is not None and stock.roe > 10.0:
                    score += 20
                    match_details.append(f"high ROE ({stock.roe}%)")
                    match_results.append(MatchResult(
                        factor="ROE",
                        paper_condition="> 10.0%",
                        stock_value=float(stock.roe),
                        is_match=True,
                        gap=round(float(stock.roe) - 10.0, 4),
                    ))

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["dividend"]):
                if stock.dividend_yield is not None and stock.dividend_yield > 3.0:
                    score += 20
                    match_details.append(f"high dividend yield ({stock.dividend_yield}%)")
                    match_results.append(MatchResult(
                        factor="Dividend Yield",
                        paper_condition="> 3.0%",
                        stock_value=float(stock.dividend_yield),
                        is_match=True,
                        gap=round(float(stock.dividend_yield) - 3.0, 4),
                    ))

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["momentum"]):
                if stock.momentum_1y is not None and stock.momentum_1y > 0:
                    score += 20
                    match_details.append(f"positive 1Y momentum ({stock.momentum_1y}%)")
                    match_results.append(MatchResult(
                        factor="Momentum 1Y",
                        paper_condition="> 0%",
                        stock_value=float(stock.momentum_1y),
                        is_match=True,
                        gap=round(float(stock.momentum_1y), 4),
                    ))

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["debt"] + self.FACTOR_SYNONYMS["volatility"]):
                if stock.debt_ratio is not None and stock.debt_ratio < 100.0:
                    score += 15
                    match_details.append(f"healthy debt ratio ({stock.debt_ratio}%)")
                    match_results.append(MatchResult(
                        factor="Debt Ratio",
                        paper_condition="< 100.0%",
                        stock_value=float(stock.debt_ratio),
                        is_match=True,
                        gap=round(float(stock.debt_ratio) - 100.0, 4),
                    ))

            if any(k in combined_strategy_text for k in self.FACTOR_SYNONYMS["size"]):
                if stock.market_cap is not None:
                    score += 10
                    match_details.append("market-cap/liquidity theme")

            has_qualitative_theme = any(
                k in combined_strategy_text
                for k in self.FACTOR_SYNONYMS["industry"] + self.FACTOR_SYNONYMS["governance"]
            )
            if has_qualitative_theme:
                match_details.append("qualitative theme match")
                match_results.append(MatchResult(
                    factor="Qualitative Theme",
                    paper_condition="Industry/Governance theme match",
                    stock_value=0.0,
                    is_match=True,
                    gap=0.0,
                ))
                if score == 0:
                    score += 5

            if score > 0:
                scored_stocks.append((stock, score, match_details, match_results))

        scored_stocks.sort(key=lambda x: x[1], reverse=True)
        return scored_stocks

    async def _batch_format_to_schema(
        self,
        top_stocks: List[Tuple],
        strategies: List[str],
    ) -> List[RecommendationResult]:
        stock_summaries = []
        for stock, score, match_details, _ in top_stocks:
            stock_summaries.append({
                "ticker": stock.ticker,
                "name": stock.name,
                "quant_score": score,
                "matched_factors": match_details,
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
                model="gpt-4o-mini",
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
        for stock, score, match_details, match_results in top_stocks:
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
                confidence_score=float(llm_info.get("confidence_score", min(99.0, score + 10.0))),
                matched_strategies=[strategies[0][:50]],
                why_this_stock=why_obj,
                match_results=match_results,
                risk_factors=llm_info.get("risk_factors", ["Market volatility risk"]),
                simple_summary=llm_info.get("simple_summary", f"{stock.name}: quant-matched candidate"),
                evidence=evidence_list,
            )
            final_results.append(result)

        return final_results
