"""Built-in scorer implementations."""

from __future__ import annotations

import re

from app.scoring.base import BaseScorer
from app.scoring import ScoringContext, ScoreResult


class ExactMatchScorer(BaseScorer):
    rule_type = "exact_match"
    score_data_type = "BOOLEAN"

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        case_sensitive = ctx.rule_config.get("case_sensitive", True)
        a = ctx.actual_output if case_sensitive else ctx.actual_output.lower()
        b = ctx.case_expected_output if case_sensitive else (ctx.case_expected_output or "").lower()
        passed = a == b
        return ScoreResult(
            rule_id=ctx.rule_config.get("_rule_id", ""),
            rule_type=self.rule_type,
            score=1.0 if passed else 0.0,
            threshold=ctx.rule_threshold,
            passed=passed,
            details={"expected": ctx.case_expected_output, "actual": ctx.actual_output},
        )


class KeywordScorer(BaseScorer):
    rule_type = "keyword"

    # English stopwords — common function words with little semantic value
    _EN_STOP = frozenset({
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall',
        'should', 'may', 'might', 'must', 'can', 'could',
        'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'as',
        'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'out', 'off', 'over', 'under', 'again', 'further',
        'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 'just', 'because', 'as', 'until', 'while',
        'it', 'its', 'this', 'that', 'these', 'those', 'i', 'me', 'my',
        'we', 'our', 'you', 'your', 'he', 'she', 'him', 'her', 'his',
        'they', 'them', 'their', 'what', 'which', 'who', 'whom',
        'and', 'but', 'or', 'if', 'while', 'the', 'up', 'down',
    })

    # Chinese stopwords — common function words
    _ZH_STOP = frozenset({
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都',
        '一', '个', '上', '也', '很', '到', '说', '要', '去', '你', '会',
        '着', '没有', '看', '好', '自己', '这', '他', '她', '它', '们',
        '那', '为', '以', '能', '下', '过', '对', '而', '之', '与', '及',
        '但', '或', '被', '把', '让', '从', '向', '并', '所', '将',
        '可以', '应该', '因为', '所以', '如果', '虽然', '但是', '因此',
        '以及', '关于', '除了', '通过', '按照', '其中', '之间', '之后',
        '之前', '以上', '以下', '左右', '目前', '当前', '同时',
        '一个', '这个', '那个', '这些', '那些', '一些', '某个', '哪个',
        '什么', '如何', '怎样', '怎么', '为什么', '哪些', '每个',
        '使用', '利用', '采用', '进行', '通过', '基于', '根据',
        '提供', '包括', '以及', '用于', '需要', '可以', '能够',
        '已经', '正在', '将会', '必须', '应该', '具有', '出现',
    })

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        exclude = ctx.rule_config.get("exclude", [])
        output_lower = (ctx.actual_output or "").lower()
        output_plain = self._normalize(output_lower)

        # Determine what to check against
        include = ctx.rule_config.get("include", [])
        if include:
            # Explicit include list → exact phrase matching (backward compatible)
            keywords = include
            source = "include"
        elif ctx.case_expected_output:
            # Auto-extract meaningful keywords from expected output
            keywords = self._extract_keywords(ctx.case_expected_output)
            source = "expected_output"
        else:
            keywords = []
            source = "none"

        # Match: for phrases (include list) use normalized matching;
        # for auto-extracted short terms, substring check is naturally robust
        if include:
            hits = [k for k in keywords if self._normalize(k.lower()) in output_plain]
        else:
            hits = [k for k in keywords if k.lower() in output_lower]

        misses = [k for k in exclude if k.lower() in output_lower]

        total = len(keywords)
        ratio = len(hits) / total if total > 0 else 0.0
        if misses:
            ratio *= 0.5

        passed = ratio >= ctx.rule_threshold and not misses
        return ScoreResult(
            rule_id=ctx.rule_config.get("_rule_id", ""),
            rule_type=self.rule_type,
            score=ratio,
            threshold=ctx.rule_threshold,
            passed=passed,
            details={
                "hits": hits,
                "misses": misses,
                "total_keywords": total,
                "source": source,
            },
        )

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text for coverage comparison.

        1) English words (2+ letters, not stopwords)
        2) Chinese character n-grams (2~4 width, sliding, not stopwords)
        3) Numeric tokens (2+ digits)
        """
        if not text:
            return []

        keywords = []

        # English words (2+ letters)
        for w in re.findall(r'[a-zA-Z]{2,}', text):
            if w.lower() not in KeywordScorer._EN_STOP:
                keywords.append(w.lower())

        # Numeric tokens (2+ digits)
        keywords.extend(re.findall(r'\d{2,}', text))

        # Chinese: sliding bigrams (2-width) from runs of CJK characters.
        # Bigrams capture meaningful word boundaries better than longer n-grams,
        # while generating manageable noise from unavoidable cross-boundary splits.
        for run in re.findall(r'[一-鿿]+', text):
            seen = set()
            for i in range(len(run) - 1):
                gram = run[i:i + 2]
                if gram not in seen and gram not in KeywordScorer._ZH_STOP:
                    seen.add(gram)
                    keywords.append(gram)

        return keywords

    @staticmethod
    def _normalize(text: str) -> str:
        """Remove common formatting markers for substring matching."""
        return re.sub(r'(\*\*|__|`|~~)', '', text)


class RegexScorer(BaseScorer):
    rule_type = "regex"
    score_data_type = "BOOLEAN"

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        pattern = ctx.rule_config.get("pattern", "")
        match_type = ctx.rule_config.get("match_type", "search")

        try:
            if match_type == "fullmatch":
                m = re.fullmatch(pattern, ctx.actual_output)
            elif match_type == "match":
                m = re.match(pattern, ctx.actual_output)
            else:
                m = re.search(pattern, ctx.actual_output)
            passed = m is not None
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=self.rule_type,
                score=1.0 if passed else 0.0,
                threshold=ctx.rule_threshold,
                passed=passed,
                details={"matched": m.group() if m else None},
            )
        except re.error as e:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=self.rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=str(e),
            )


class DurationScorer(BaseScorer):
    rule_type = "duration"
    score_data_type = "BOOLEAN"

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        max_ms = ctx.rule_config.get("max_ms", 30_000)
        min_ms = ctx.rule_config.get("min_ms", 0)
        duration = ctx.rule_config.get("_response_time_ms", 0)
        passed = min_ms <= duration <= max_ms
        return ScoreResult(
            rule_id=ctx.rule_config.get("_rule_id", ""),
            rule_type=self.rule_type,
            score=1.0 if passed else 0.0,
            threshold=ctx.rule_threshold,
            passed=passed,
            details={"duration_ms": duration, "min_ms": min_ms, "max_ms": max_ms},
        )


class LengthScorer(BaseScorer):
    rule_type = "length"
    score_data_type = "BOOLEAN"

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        min_chars = ctx.rule_config.get("min_chars", 0)
        max_chars = ctx.rule_config.get("max_chars", 10_000)
        length = len(ctx.actual_output)
        passed = min_chars <= length <= max_chars
        return ScoreResult(
            rule_id=ctx.rule_config.get("_rule_id", ""),
            rule_type=self.rule_type,
            score=1.0 if passed else 0.0,
            threshold=ctx.rule_threshold,
            passed=passed,
            details={"length": length, "min_chars": min_chars, "max_chars": max_chars},
        )
