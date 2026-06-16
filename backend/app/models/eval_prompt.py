"""EvalPromptTemplate model — structured prompt template for AI evaluation."""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON

from app.models.base import Base


class EvalPromptTemplate(Base):
    __tablename__ = "eval_prompt_templates"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Evaluation strategy
    strategy = Column(String(20), nullable=False, default="simple")
    # simple | reference | rubric | pairwise | chain_of_thought | few_shot

    # Structured prompt sections (Jinja2)
    system_prompt = Column(Text, nullable=True)           # System-level instructions
    user_prompt_template = Column(Text, nullable=False)    # User message template (Jinja2)

    # Output format — JSON schema for structured output parsing
    output_schema = Column(JSON, nullable=True)
    # Example: {"score": "number 0-1", "reasoning": "string", "dimensions": {"accuracy": "number"}}

    # Few-shot examples (for few_shot strategy)
    few_shot_examples = Column(JSON, nullable=True)
    # [{"input": "...", "expected_output": "...", "actual_output": "...", "score": 0.9, "reasoning": "..."}]

    # Variables declared for this template (auto-extracted or manual)
    variables = Column(JSON, nullable=False, default=[])

    # Deprecated — kept for backward compatibility, migrate to user_prompt_template
    template_content = Column(Text, nullable=True)

    # Metadata
    output_format = Column(String(20), nullable=False, default="json")  # json / text / score_only
    version = Column(String(20), nullable=False, default="1.0")
    is_builtin = Column(Boolean, nullable=False, default=False)
    tags = Column(JSON, nullable=True)  # categorization tags
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    space_id = Column(String(36), ForeignKey("spaces.id"), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
