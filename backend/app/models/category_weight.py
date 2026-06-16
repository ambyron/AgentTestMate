"""CategoryWeight model — per-task category weight override."""

from sqlalchemy import Column, String, Float, ForeignKey, UniqueConstraint

from app.models.base import Base


class CategoryWeight(Base):
    __tablename__ = "category_weights"
    __table_args__ = (
        UniqueConstraint("task_id", "category", name="uq_task_category"),
    )

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
