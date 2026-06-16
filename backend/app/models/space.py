"""Space model — one user has exactly one space for resource isolation."""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func

from app.models.base import Base


class Space(Base):
    __tablename__ = "spaces"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
