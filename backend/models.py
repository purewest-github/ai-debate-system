from enum import Enum
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
import time


class AIName(str, Enum):
    CLAUDE = "Claude"
    CHATGPT = "ChatGPT"
    GEMINI = "Gemini"
    GROK = "Grok"


class ResponseType(str, Enum):
    INITIAL = "initial"
    EVALUATION = "evaluation"
    REVISION = "revision"
    SCORING = "scoring"


class DebateResponse(BaseModel):
    id: str
    ai: AIName
    round: int
    response_type: ResponseType
    phase: str
    target_ai: Optional[AIName] = None
    revision_of: Optional[str] = None
    content: str
    error: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class ScoreDetail(BaseModel):
    scorer_ai: AIName
    target_ai: AIName
    is_self: bool
    accuracy: float
    evidence: float
    consistency: float
    coverage: float
    usefulness: float
    brevity: float
    revision_quality: float
    weighted_total: float
    reason: str


class DebateConfig(BaseModel):
    question: str
    rounds: int = Field(default=2, ge=1, le=5)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    grok_api_key: str = ""
    enabled_ais: List[AIName] = Field(default_factory=lambda: list(AIName))
    language: Literal["ja", "en"] = "ja"
    enable_revision: bool = True
    max_tokens_initial: int = 1000
    max_tokens_eval: int = 3000
    max_tokens_revision: int = 1500
    max_tokens_score: int = 3000
    model_eval: str = ""
    model_revision: str = ""
    model_scoring: str = ""
