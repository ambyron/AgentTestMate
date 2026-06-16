"""ScoreConfig model — defines data type and constraints for scoring."""

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class ScoreConfig(Base):
    __tablename__ = "score_configs"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    data_type = Column(String(20), nullable=False)  # NUMERIC / BOOLEAN / CATEGORICAL
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    categories = Column(JSON, nullable=True)  # [{label, value}] for CATEGORICAL
    default = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
