"""TestCase model."""

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("dataset_id", "case_id", name="uq_dataset_case"),
    )

    id = Column(String(36), primary_key=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    case_id = Column(String(255), nullable=False)
    input = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=True)
    categories = Column(JSON, nullable=False, default=[])
    objectives = Column(JSON, nullable=False, default=[])
    rule_refs = Column(JSON, nullable=True, default=[])
    tags = Column(JSON, nullable=True, default=[])
    metadata_ = Column("metadata", JSON, nullable=True, default={})
    sort_order = Column(Integer, nullable=False, default=0)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
