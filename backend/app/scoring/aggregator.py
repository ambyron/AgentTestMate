"""ScoreAggregator — objective-weighted scoring (categories removed)."""

from __future__ import annotations

from app.scoring import AggregatedScores, ObjectiveScore, ScoreResult


class ScoreAggregator:
    """Aggregates individual ScoreResults into objective and total scores.

    Formula:
        objective_score = Σ(rule_score × rule_weight) / Σ(rule_weight)
        total_score     = Σ(objective_score × objective_weight) / Σ(objective_weight)
    """

    def aggregate(
        self,
        score_results: list[ScoreResult],
        case_objectives: list[str],
        rule_objective_map: dict[str, list[str]],
        objective_weights: dict[str, float],
        objective_thresholds: dict[str, float],
        global_threshold: float = 0.7,
    ) -> AggregatedScores:
        # 1. Group by objective
        obj_scores: dict[str, list[ScoreResult]] = {}
        for sr in score_results:
            objectives = rule_objective_map.get(sr.rule_id, case_objectives)
            for obj in objectives:
                obj_scores.setdefault(obj, []).append(sr)

        # 2. Per-objective
        objective_results: dict[str, ObjectiveScore] = {}
        for obj_name in case_objectives:
            scores = obj_scores.get(obj_name, [])
            if not scores:
                continue
            total_w = sum(s.threshold for s in scores if s.score > 0) or len(scores)
            weighted = sum(s.score * s.threshold for s in scores) / total_w if scores else 0
            w = objective_weights.get(obj_name, 1.0)
            t = objective_thresholds.get(obj_name, 0.7)
            objective_results[obj_name] = ObjectiveScore(
                name=obj_name, score=weighted, weight=w, threshold=t, passed=weighted >= t,
            )

        # 3. Global (directly from objectives, no category level)
        total_w = sum(o.weight for o in objective_results.values())
        final_score = sum(o.score * o.weight for o in objective_results.values()) / total_w if total_w > 0 else 0
        passed = final_score >= global_threshold if objective_results else False

        return AggregatedScores(
            total_score=final_score,
            passed=passed,
            objective_scores=objective_results,
            category_scores={},
        )
