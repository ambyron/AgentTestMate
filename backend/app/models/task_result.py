"""TaskResult model — result of a single test case execution."""

from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class TaskResult(Base):
    __tablename__ = "task_results"

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    case_id = Column(String(255), nullable=False)

    # Raw execution data
    raw_input = Column(Text, nullable=False)
    raw_output = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    status_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    # Scoring
    passed = Column(Boolean, nullable=False, default=False)
    total_score = Column(Float, nullable=False, default=0.0)
    scores = Column(JSON, nullable=False, default=dict)

    # AI judge details
    ai_eval_detail = Column(JSON, nullable=True)
    ai_arbitration_result = Column(JSON, nullable=True)

    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    executed_at = Column(DateTime, nullable=False, server_default=func.now())
