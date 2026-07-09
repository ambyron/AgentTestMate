"""ScoreAggregator — unified rule scoring with objective breakdown.

Three scenarios:
  A. case_objectives matched to rules → objective-weighted scoring
  B. case_objectives exist but no rules match → direct rule averaging
  C. case_objectives empty → direct rule averaging

Formula:
    objective_score = Σ(rule_score × threshold) / Σ(threshold)
    total_score     = Σ(objective_score × objective_weight) / Σ(objective_weight)
    fallback        = Σ(rule_score × threshold) / Σ(threshold)
"""

from __future__ import annotations

from app.scoring import AggregatedScores, ObjectiveScore, ScoreResult


class ScoreAggregator:
    """Aggregates individual ScoreResults into objective and total scores."""

    @staticmethod
    def _direct_score(scores: list[ScoreResult]) -> float:
        """Weighted average using threshold as weight."""
        total_w = sum(s.threshold for s in scores if s.score > 0) or len(scores)
        return sum(s.score * s.threshold for s in scores) / total_w if total_w > 0 else 0.0

    def aggregate(
        self,
        score_results: list[ScoreResult],
        case_objectives: list[str],
        rule_objective_map: dict[str, list[str]],
        objective_weights: dict[str, float],
        objective_thresholds: dict[str, float],
        global_threshold: float = 0.7,
    ) -> AggregatedScores:
        if not score_results:
            return AggregatedScores(total_score=0.0, passed=False, objective_scores={}, category_scores={})

        # 1. Group by objective
        obj_scores: dict[str, list[ScoreResult]] = {}
        for sr in score_results:
            objectives = rule_objective_map.get(sr.rule_id, case_objectives)
            for obj in objectives:
                obj_scores.setdefault(obj, []).append(sr)

        # 2. Per-objective (only when case objectives exist)
        objective_results: dict[str, ObjectiveScore] = {}
        if case_objectives:
            for obj_name in case_objectives:
                scores = obj_scores.get(obj_name, [])
                if not scores:
                    continue
                weighted = self._direct_score(scores)
                w = objective_weights.get(obj_name, 1.0)
                t = objective_thresholds.get(obj_name, 0.7)
                objective_results[obj_name] = ObjectiveScore(
                    name=obj_name, score=weighted, weight=w, threshold=t, passed=weighted >= t,
                )

        # 3. Calculate final score
        if objective_results:
            # Scenario A: objectives matched → weighted by objective weight
            total_w = sum(o.weight for o in objective_results.values())
            final_score = sum(o.score * o.weight for o in objective_results.values()) / total_w if total_w > 0 else 0.0
        else:
            # Scenario B/C: no objective match or no objectives → direct rule averaging
            final_score = self._direct_score(score_results)

        passed = final_score >= global_threshold if (score_results or objective_results) else False

        return AggregatedScores(
            total_score=final_score,
            passed=passed,
            objective_scores=objective_results,
            category_scores={},
        )
