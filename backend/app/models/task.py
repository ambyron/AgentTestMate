"""Task model — an evaluation task."""

from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)
    display_id = Column(String(6), nullable=False, unique=True)  # 六位展示ID, 如 000001
    name = Column(String(255), nullable=False)
    agent_ids = Column(JSON, nullable=False, default=[])
    dataset_ids = Column(JSON, nullable=False, default=[])
    filters = Column(JSON, nullable=True, default={})
    config = Column(JSON, nullable=False, default={})  # concurrency, timeout, retries
    ai_scoring_config = Column(JSON, nullable=True, default={})
    status = Column(String(20), nullable=False, default="pending")  # pending/running/paused/completed/failed/cancelled
    progress = Column(JSON, nullable=False, default={"total": 0, "completed": 0, "failed": 0, "passed": 0})
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
