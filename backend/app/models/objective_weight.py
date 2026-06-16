"""ObjectiveWeight model — per-task objective weight & threshold override."""

from sqlalchemy import Column, String, Float, ForeignKey, UniqueConstraint

from app.models.base import Base


class ObjectiveWeight(Base):
    __tablename__ = "objective_weights"
    __table_args__ = (
        UniqueConstraint("task_id", "objective", name="uq_task_objective"),
    )

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    objective = Column(String(100), nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    threshold = Column(Float, nullable=True)
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
