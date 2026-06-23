from typing import List, Dict

class StrategyFewShotPool:
    """
    [Teacher-Student 패턴]
    GPT-4o(비싸고 똑똑한 모델)가 완벽하게 추출해낸 황금 예시(Golden Examples) 모음.
    GPT-4o-mini(싸고 빠른 모델)에게 이 예시를 주입하여 환각을 방지하고 스키마를 강제함.
    """
    
    @staticmethod
    def get_paper_extraction_examples() -> List[Dict[str, str]]:
        return [
            {
                "role": "user",
                "content": "논문 텍스트: 'We sorted stocks based on their book-to-market ratio. The top 20% portfolio showed an annualized excess return of 5.2% over 5 years. This value effect was robust across large and mid-cap stocks, excluding financial sectors.'"
            },
            {
                "role": "assistant",
                "content": """```json
{
  "strategies": [
    {
      "name": "저 PBR (Book-to-Market 상위 20% 가치주) 전략",
      "conditions": [
        {"factor": "PBR", "operator": "<", "value": 1.0, "unit": "ratio"} 
      ],
      "performance": {
        "return_type": "excess",
        "return_value": 5.2,
        "benchmark": "시장 평균"
      },
      "valid_condition": {
        "period": "5년",
        "market": "미국 (추정)",
        "sectors": ["전체"],
        "exclude": ["금융"]
      },
      "risk_notes": ["금융주 제외 필요"],
      "confidence": "high"
    }
  ]
}
```"""
            }
        ]