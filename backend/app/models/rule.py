"""Rule model — scoring rule definition."""

from sqlalchemy import Column, String, Text, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class Rule(Base):
    __tablename__ = "rules"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False)  # exact_match / keyword / regex / ...
    config = Column(JSON, nullable=False, default={})
    objectives = Column(JSON, nullable=False, default=[])
    weight = Column(Float, nullable=False, default=1.0)
    threshold = Column(Float, nullable=False, default=0.8)
    enabled = Column(Boolean, nullable=False, default=True)

    # ScoreConfig reference (data type constraints)
    score_config_id = Column(String(36), ForeignKey("score_configs.id"), nullable=True)

    # AI judge fields (nullable for non-AI rules)
    ai_judge_model_id = Column(String(36), ForeignKey("ai_judge_models.id"), nullable=True)
    ai_eval_prompt_id = Column(String(36), ForeignKey("eval_prompt_templates.id"), nullable=True)
    ai_rubric_id = Column(String(36), ForeignKey("scoring_rubrics.id"), nullable=True)
    eval_strategy = Column(String(20), nullable=True)  # simple/reference/rubric/chain_of_thought/few_shot/pairwise

    custom_script = Column(Text, nullable=True)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
