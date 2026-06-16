"""Annotation model — human review of task results."""

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, func

from app.models.base import Base


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(String(36), primary_key=True)
    task_result_id = Column(String(36), ForeignKey("task_results.id"), nullable=False)
    score = Column(Float, nullable=False)
    comment = Column(Text, nullable=True)
    label = Column(String(50), nullable=True)  # correct / incorrect / needs_review
    annotator = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending / approved / rejected
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
