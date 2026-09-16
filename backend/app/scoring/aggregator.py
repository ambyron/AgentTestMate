"""ScoreAggregator — objective-weighted scoring rule aggregation.

Scenarios:
  A. case_objectives matches rules → objective-weighted scoring
  B. case_objectives empty → use all_rule_objectives as implicit objectives
  C. case_objectives exist but no rules match → unscored objectives handled via else

Failure handling (evaluation_failed):
  Rules whose evaluator itself failed (AI judge timeout / network / parse error)
  are excluded from the objective average, so a transient judge glitch does not
  silently drag a case's score to 0. If EVERY rule for a case failed, the case is
  reported as an *evaluation failure* rather than a genuine low score.

Formula (simple average within objective):
    objective_score = Σ(rule_score of usable rules) / len(usable rules)
    total_score     = Σ(objective_score × objective_weight) / Σ(objective_weight)
"""

from __future__ import annotations

from app.scoring import AggregatedScores, ObjectiveScore, ScoreResult


class ScoreAggregator:
    """Aggregates individual ScoreResults into objective and total scores."""

    @staticmethod
    def _avg_score(scores: list[ScoreResult]) -> float:
        """Simple average of scores."""
        return sum(s.score for s in scores) / len(scores) if scores else 0.0

    def aggregate(
        self,
        score_results: list[ScoreResult],
        case_objectives: list[str],
        rule_objective_map: dict[str, list[str]],
        objective_weights: dict[str, float],
        objective_thresholds: dict[str, float],
        global_threshold: float = 0.7,
        all_rule_objectives: list[str] | None = None,
    ) -> AggregatedScores:
        if not score_results:
            return AggregatedScores(
                total_score=0.0, passed=False, objective_scores={},
                category_scores={}, evaluation_failed=True, failed_rule_count=0,
            )

        # 0. Split usable results from evaluator failures.
        #    Failed rules keep score=0.0 for the record but must not be averaged in.
        usable = [sr for sr in score_results if not sr.evaluation_failed]
        failed_count = len(score_results) - len(usable)

        # Every rule failed → this case tells us nothing about quality.
        if not usable:
            return AggregatedScores(
                total_score=0.0,
                passed=False,          # never reward an evaluator outage
                objective_scores={},
                category_scores={},
                evaluation_failed=True,
                failed_rule_count=failed_count,
            )

        # 1. Determine effective objectives
        if not case_objectives and all_rule_objectives:
            # Scenario B: empty case → inherit all rule objectives
            effective_objectives = all_rule_objectives
        else:
            effective_objectives = case_objectives

        # 2. Group by objective (usable rules only)
        obj_scores: dict[str, list[ScoreResult]] = {}
        for sr in usable:
            objectives = rule_objective_map.get(sr.rule_id, effective_objectives)
            for obj in objectives:
                obj_scores.setdefault(obj, []).append(sr)

        # 3. Per-objective scoring
        objective_results: dict[str, ObjectiveScore] = {}
        if effective_objectives:
            for obj_name in effective_objectives:
                scores = obj_scores.get(obj_name, [])
                if not scores:
                    continue
                avg = self._avg_score(scores)
                w = objective_weights.get(obj_name, 1.0)
                t = objective_thresholds.get(obj_name, 0.7)
                objective_results[obj_name] = ObjectiveScore(
                    name=obj_name, score=avg, weight=w, threshold=t, passed=avg >= t,
                )

        # 4. Calculate final score
        if objective_results:
            total_w = sum(o.weight for o in objective_results.values())
            final_score = sum(o.score * o.weight for o in objective_results.values()) / total_w if total_w > 0 else 0.0
        else:
            final_score = self._avg_score(usable)

        passed = final_score >= global_threshold

        return AggregatedScores(
            total_score=final_score,
            passed=passed,
            objective_scores=objective_results,
            category_scores={},
            evaluation_failed=False,
            failed_rule_count=failed_count,
        )
