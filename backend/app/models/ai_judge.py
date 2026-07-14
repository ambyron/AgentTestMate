"""AI Judge model — represents an LLM used for evaluation scoring."""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class AIJudgeModel(Base):
    __tablename__ = "ai_judge_models"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)  # openai / anthropic / google / azure / custom
    model_name = Column(String(255), nullable=False)
    api_base_url = Column(String(2048), nullable=False)
    auth_type = Column(String(20), nullable=False, default="api_key")
    auth_credentials = Column(Text, nullable=True)  # encrypted
    headers_template = Column(JSON, nullable=True)  # custom HTTP headers for enterprise gateways
    parameters = Column(JSON, nullable=False, default={})  # temperature, max_tokens, etc.
    status = Column(String(20), nullable=False, default="active")  # active / inactive
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
