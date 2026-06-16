"""Objective model — evaluation objective."""

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, func

from app.models.base import Base


class Objective(Base):
    __tablename__ = "objectives"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    default_weight = Column(Float, nullable=False, default=1.0)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
