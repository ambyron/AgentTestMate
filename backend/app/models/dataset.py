"""Dataset model."""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset_type = Column(String(100), nullable=True)
    version = Column(String(20), nullable=False, default="1.0")
    tags = Column(JSON, nullable=False, default=[])
    is_builtin = Column(Boolean, nullable=False, default=False)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
