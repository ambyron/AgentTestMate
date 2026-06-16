"""ScoringRubric model — multi-dimension scoring rubric."""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class ScoringRubric(Base):
    __tablename__ = "scoring_rubrics"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dimensions = Column(JSON, nullable=False, default=[])
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
