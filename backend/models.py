from enum import Enum
from typing import Optional, List
from pydantic import BaseModel
import time


class AIName(str, Enum):
    CLAUDE  = "Claude"
    CHATGPT = "ChatGPT"
    GEMINI  = "Gemini"
    GROK    = "Grok"


class SceneName(str, Enum):
    IMPLEMENTATION = "implementation"
    DECISION       = "decision"
    LOGIC_CHECK    = "logic_check"
    RESEARCH       = "research"


class StepRole(str, Enum):
    LEAD                = "lead"
    SUPPORT_CRITIC      = "support_critic"
    SUPPORT_ORGANIZER   = "support_organizer"
    SUPPORT_VALIDATOR   = "support_validator"
    SUPPORT_EXECUTOR    = "support_executor"
    SUPPORT_REWRITER    = "support_rewriter"
    SUPPORT_CONFIDENCE  = "support_confidence"
    SUPPORT_UNCERTAINTY = "support_uncertainty"
    SUPPORT_HYPOTHESIS  = "support_hypothesis"
    SCORER              = "scorer"


class FlowType(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL   = "parallel"


class FlowStep(BaseModel):
    step_index: int
    ai: AIName
    role: StepRole
    flow_type: FlowType
    prompt_key: str
    depends_on: List[int] = []


class SceneConfig(BaseModel):
    scene: SceneName
    steps: List[FlowStep]
    scorer_available: bool
    scorer_default: bool


class FlowRequest(BaseModel):
    question: str
    scene: SceneName
    enable_scorer: bool
    openai_api_key: str
    gemini_api_key: str
    grok_api_key: str
    language: str = "ja"
    model_overrides: dict = {}


class StepResponse(BaseModel):
    id: str
    step_index: int
    ai: AIName
    role: StepRole
    content: str
    error: Optional[str] = None
    timestamp: float = 0.0


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


class DetectRequest(BaseModel):
    question: str
    gemini_api_key: str


class DetectResponse(BaseModel):
    scene: SceneName
    confidence: float
    reason: str
