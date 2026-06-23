import logging
import json
from typing import List, Dict, Any
from shared.schemas.paper import ExtractedStrategy
from shared.utils.validators import validate_paper_strategies
from backend.fastapi_app.rag.embedder import QuantEmbedder
from backend.fastapi_app.rag.retriever import ChromaVectorStore

logger = logging.getLogger(__name__)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_strategy_payload(raw_json: str) -> str:
    data = json.loads(raw_json)
    strategies = data.get("strategies", [])

    for strategy in strategies:
        if "name" not in strategy:
            strategy["name"] = (
                strategy.get("strategy_name")
                or strategy.get("name")
                or str(strategy.get("strategy_fit") or "paper-derived strategy")
            )

        strategy["strategy_fit"] = [str(v) for v in _as_list(strategy.get("strategy_fit")) if v]
        strategy["key_findings"] = [str(v) for v in _as_list(strategy.get("key_findings")) if v]

    data["strategies"] = strategies
    return json.dumps(data, ensure_ascii=False)

class PaperProcessor:
    def __init__(self, openai_client, embedder: QuantEmbedder, vector_store: ChromaVectorStore):
        self.openai_client = openai_client
        self.embedder = embedder
        self.vector_store = vector_store

    async def extract_and_store(self, chunk_text: str, paper_meta: Dict[str, Any]):
        """
        LLM을 통해 논문 텍스트에서 퀀트 전략을 추출하고, 
        데이터 충족도(Completeness)를 계산하여 벡터DB에 적재합니다.
        """
        system_prompt = """
        너는 금융/퀀트 논문에서 투자 전략을 추출하는 최고 수준의 AI 데이터 분석가야.
        아래 제공되는 논문의 텍스트를 읽고, 투자 전략을 추출해서 반드시 **JSON 형식**으로 응답해.

        [중요 규칙]
        1. 응답은 반드시 `{"strategies": [ { ... } ] }` 형태의 완벽한 JSON이어야 해. 다른 설명은 일절 덧붙이지 마.
        2. 명확한 수치(PER < 10 등)나 성과(performance)가 없더라도, 초록의 문맥을 파악해서 'strategy_fit'(적합 팩터)나 'key_findings'(핵심 근거)를 반드시 추출해. 
        3. 절대 추출을 포기하거나 빈 배열을 반환하지 마.
        4. confidence는 "high", "medium", "low" 중 하나로 작성해.
        """
        
        try:
            # 1. LLM 전략 추출
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"다음 텍스트에서 퀀트 전략을 추출해:\n\n{chunk_text}"}
                ],
                temperature=0.1
            )
            
            raw_json = normalize_strategy_payload(response.choices[0].message.content)
            strategies: List[ExtractedStrategy] = validate_paper_strategies(raw_json)
            
            if not strategies:
                logger.warning(f"⚠ [Processor] {paper_meta.get('title')} - 추출 전략 없음 (빈 리스트 반환)")
                return

            # 2. 벡터DB 적재 준비
            ids, documents, metadatas = [], [], []
            
            for idx, strategy in enumerate(strategies):
                # 데이터 충족도 계산 및 메타데이터 주입
                strategy.data_completeness = strategy.compute_completeness()
                strategy.paper_id = paper_meta.get("paperId", "unknown")
                strategy.paper_title = paper_meta.get("title", "unknown")
                
                # [방어 로직 적용] 값이 존재하는(None이 아닌) 필드만 텍스트로 조립
                doc_lines = [f"전략명: {strategy.name}"]
                
                if strategy.strategy_fit:
                    doc_lines.append(f"적합 팩터/테마: {', '.join(strategy.strategy_fit)}")
                    
                if strategy.key_findings:
                    doc_lines.append(f"핵심 근거: {' '.join(strategy.key_findings)}")
                    
                if strategy.conditions:
                    cond_texts = []
                    for c in strategy.conditions:
                        if hasattr(c, 'operator') and c.operator and hasattr(c, 'value') and c.value:
                            cond_texts.append(f"{c.factor} {c.operator} {c.value} {c.unit}")
                    if cond_texts:
                        doc_lines.append(f"조건: {', '.join(cond_texts)}")
                        
                if strategy.performance:
                    doc_lines.append(f"백테스트 성과: {strategy.performance.return_type} 수익률 {strategy.performance.return_value}%")
                
                doc_text = "\n".join(doc_lines)
                
                ids.append(f"{strategy.paper_id}_strat_{idx}")
                documents.append(doc_text)
                
                metadatas.append({
                    "paper_id": strategy.paper_id,
                    "title": strategy.paper_title,
                    "completeness": float(strategy.data_completeness)
                })

            # 3. 임베딩 및 비동기 적재
            embeddings = await self.embedder.get_embeddings(documents)
            if embeddings:
                await self.vector_store.add_papers_async(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"✅ [Processor] {strategy.paper_title[:15]}... - 전략 {len(ids)}개 벡터DB 적재 완료")

        except Exception as e:
            logger.error(f"🚨 [Processor Error] 추출 및 적재 실패: {e}")
