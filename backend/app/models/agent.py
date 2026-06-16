"""Agent model — represents a tested agent API."""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    api_base_url = Column(String(2048), nullable=False)
    method = Column(String(10), nullable=False, default="POST")  # GET / POST / PUT
    auth_type = Column(String(20), nullable=False, default="none")  # none / api_key / bearer / basic
    auth_credentials = Column(String(2048), nullable=True)  # encrypted
    headers_template = Column(JSON, nullable=False, default={})
    body_template = Column(JSON, nullable=False, default={})
    timeout_ms = Column(Integer, nullable=False, default=30_000)
    status = Column(String(20), nullable=False, default="active")  # active / inactive
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
