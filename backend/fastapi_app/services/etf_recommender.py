from shared.schemas.etf import EtfRawData


class EtfRecommender:
    THEMES = {
        "semiconductor": ["반도체", "semiconductor", "chip", "hbm", "소부장", "파운드리", "팹리스", "메모리", "필라델피아반도체"],
        "battery": ["2차전지", "배터리", "전기차", "ev", "secondary battery"],
        "ai": ["ai", "인공지능", "로봇", "클라우드", "빅테크", "테크"],
        "growth": ["성장", "고성장", "나스닥", "미국나스닥", "혁신"],
        "defensive": ["안정", "방어", "저변동", "low vol", "low volatility", "리스크"],
        "dividend": ["배당", "인컴", "현금흐름", "커버드콜", "월배당"],
        "bond": ["채권", "국채", "금리", "t-bill", "cd금리", "회사채"],
        "domestic": ["국내", "한국", "코스피", "코스닥", "200"],
        "global": ["해외", "미국", "글로벌", "s&p", "sp500", "nasdaq"],
        "commodity": ["금", "원자재", "은", "구리", "gold", "commodity"],
    }

    REQUIRED_ONLY_THEMES = {"semiconductor", "battery", "ai", "dividend", "bond", "commodity"}

    def __init__(self, repo):
        self.repo = repo

    def recommend(self, query: str, limit: int = 5):
        payload = self.repo.load_payload()
        rows = self.repo.get_all()
        query_lower = (query or "").lower()

        active_themes = {
            theme for theme, words in self.THEMES.items()
            if any(word in query_lower for word in words)
        }

        if not active_themes:
            active_themes = {"growth"}

        scored = []
        for etf in rows:
            if etf.leveraged or etf.inverse:
                continue

            name = (etf.name or "").lower()
            category = (etf.category or "").lower()
            matches = self._build_match_map(name, category)

            if not self._theme_gate(active_themes, matches):
                continue

            score, reasons, available, total = 0.0, [], 0.0, 0.0

            def add(label, value, weight, normalizer, good=None):
                nonlocal score, available, total
                total += weight
                if value is None:
                    return
                available += weight
                strength = max(0.0, min(1.0, normalizer(float(value))))
                score += weight * strength
                if good is None or good(float(value)):
                    reasons.append(f"{label} {value:g}")

            add("1년 수익률", etf.return_1y, 20, lambda v: (v + 20) / 70, lambda v: v > 0)
            add("Sharpe", etf.sharpe_1y, 20, lambda v: (v + 0.5) / 2.5, lambda v: v > 0.5)
            add("변동성", etf.volatility_1y, 15, lambda v: (50 - v) / 40, lambda v: v < 25)
            add("MDD", etf.max_drawdown_1y, 15, lambda v: (v + 50) / 45, lambda v: v > -20)
            add("NAV 괴리율", abs(etf.nav_deviation) if etf.nav_deviation is not None else None,
                10, lambda v: (2 - v) / 2, lambda v: v < 1)
            add("거래대금", etf.trading_value, 10, lambda v: v / 500_000, lambda v: v > 50_000)
            add("순자산", etf.market_cap, 10, lambda v: v / 100_000, lambda v: v > 10_000)

            if available == 0:
                continue

            theme_bonus = self._theme_bonus(active_themes, matches, etf)
            coverage = available / total
            final = min(100, score / available * 85 + theme_bonus)

            scored.append({
                **etf.model_dump(mode="json"),
                "recommendation_score": round(final, 2),
                "confidence_score": round(final * (0.7 + coverage * 0.3), 2),
                "reasons": reasons[:6],
                "data_coverage": round(coverage * 100, 1),
                "theme_match": sorted([theme for theme, ok in matches.items() if ok]),
            })

        scored.sort(key=lambda row: row["recommendation_score"], reverse=True)
        return {
            "generated_at": payload.get("generated_at"),
            "limitations": payload.get("limitations", []),
            "etfs": scored[:limit],
        }

    def _build_match_map(self, name: str, category: str):
        return {
            "semiconductor": self._has_any(name, self.THEMES["semiconductor"]) or "반도체" in category,
            "battery": self._has_any(name, self.THEMES["battery"]) or "2차전지" in category,
            "ai": self._has_any(name, self.THEMES["ai"]),
            "growth": self._has_any(name, self.THEMES["growth"]),
            "defensive": self._has_any(name, self.THEMES["defensive"]),
            "dividend": self._has_any(name, self.THEMES["dividend"]),
            "bond": self._has_any(name, self.THEMES["bond"]),
            "domestic": "국내" in category or self._has_any(name, self.THEMES["domestic"]),
            "global": "해외" in category or self._has_any(name, self.THEMES["global"]),
            "commodity": self._has_any(name, self.THEMES["commodity"]),
        }

    def _theme_gate(self, active_themes, matches):
        specific = active_themes & self.REQUIRED_ONLY_THEMES
        if specific:
            return all(matches[theme] for theme in specific)
        if "domestic" in active_themes and not matches["domestic"]:
            return False
        if "global" in active_themes and not matches["global"]:
            return False
        if "growth" in active_themes and not (matches["growth"] or matches["ai"] or matches["semiconductor"] or matches["battery"]):
            return False
        return True

    def _theme_bonus(self, active_themes, matches, etf):
        bonus = 0
        if "semiconductor" in active_themes and matches["semiconductor"]:
            bonus += 35
        if "battery" in active_themes and matches["battery"]:
            bonus += 32
        if "ai" in active_themes and matches["ai"]:
            bonus += 25
        if "growth" in active_themes and matches["growth"]:
            bonus += 12
        if "defensive" in active_themes:
            bonus += max(0, 15 - (etf.volatility_1y or 50) * 0.4)
        if "dividend" in active_themes and matches["dividend"]:
            bonus += 18
        if "bond" in active_themes and matches["bond"]:
            bonus += 20
        if "domestic" in active_themes and matches["domestic"]:
            bonus += 12
        if "global" in active_themes and matches["global"]:
            bonus += 12
        if "commodity" in active_themes and matches["commodity"]:
            bonus += 18
        return bonus

    @staticmethod
    def _has_any(text: str, tokens) -> bool:
        return any(token in text for token in tokens)
