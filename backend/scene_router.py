"""
シーンごとの SceneConfig（FlowStep のリスト）を定義・返す。
"""
from models import AIName, SceneName, StepRole, FlowType, FlowStep, SceneConfig


def get_scene_config(scene: SceneName) -> SceneConfig:
    """4シーンの SceneConfig を返す。"""
    if scene == SceneName.IMPLEMENTATION:
        return SceneConfig(
            scene=scene,
            scorer_available=True,
            scorer_default=False,
            steps=[
                FlowStep(
                    step_index=0,
                    ai=AIName.CHATGPT,
                    role=StepRole.LEAD,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="lead_implementation",
                    depends_on=[],
                ),
                FlowStep(
                    step_index=1,
                    ai=AIName.CLAUDE,
                    role=StepRole.SUPPORT_CRITIC,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="support_critic",
                    depends_on=[0],
                ),
                FlowStep(
                    step_index=2,
                    ai=AIName.GROK,
                    role=StepRole.SUPPORT_ORGANIZER,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="support_organizer",
                    depends_on=[0, 1],
                ),
            ],
        )

    if scene == SceneName.DECISION:
        return SceneConfig(
            scene=scene,
            scorer_available=True,
            scorer_default=True,
            steps=[
                FlowStep(
                    step_index=0,
                    ai=AIName.CLAUDE,
                    role=StepRole.LEAD,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="lead_decision",
                    depends_on=[],
                ),
                FlowStep(
                    step_index=1,
                    ai=AIName.GEMINI,
                    role=StepRole.SUPPORT_VALIDATOR,
                    flow_type=FlowType.PARALLEL,
                    prompt_key="support_validator",
                    depends_on=[0],
                ),
                FlowStep(
                    step_index=2,
                    ai=AIName.CHATGPT,
                    role=StepRole.SUPPORT_EXECUTOR,
                    flow_type=FlowType.PARALLEL,
                    prompt_key="support_executor",
                    depends_on=[0],
                ),
            ],
        )

    if scene == SceneName.LOGIC_CHECK:
        return SceneConfig(
            scene=scene,
            scorer_available=True,
            scorer_default=True,
            steps=[
                FlowStep(
                    step_index=0,
                    ai=AIName.CLAUDE,
                    role=StepRole.LEAD,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="lead_logic_check",
                    depends_on=[],
                ),
                FlowStep(
                    step_index=1,
                    ai=AIName.CHATGPT,
                    role=StepRole.SUPPORT_REWRITER,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="support_rewriter",
                    depends_on=[0],
                ),
                FlowStep(
                    step_index=2,
                    ai=AIName.GEMINI,
                    role=StepRole.SUPPORT_CONFIDENCE,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="support_confidence",
                    depends_on=[0, 1],
                ),
            ],
        )

    if scene == SceneName.RESEARCH:
        return SceneConfig(
            scene=scene,
            scorer_available=True,
            scorer_default=False,
            steps=[
                FlowStep(
                    step_index=0,
                    ai=AIName.GROK,
                    role=StepRole.LEAD,
                    flow_type=FlowType.SEQUENTIAL,
                    prompt_key="lead_research",
                    depends_on=[],
                ),
                FlowStep(
                    step_index=1,
                    ai=AIName.GEMINI,
                    role=StepRole.SUPPORT_UNCERTAINTY,
                    flow_type=FlowType.PARALLEL,
                    prompt_key="support_uncertainty",
                    depends_on=[0],
                ),
                FlowStep(
                    step_index=2,
                    ai=AIName.CLAUDE,
                    role=StepRole.SUPPORT_HYPOTHESIS,
                    flow_type=FlowType.PARALLEL,
                    prompt_key="support_hypothesis",
                    depends_on=[0],
                ),
            ],
        )

    raise ValueError(f"未知のシーン: {scene}")


# シーン一覧メタデータ（GET /api/scenes 用）
SCENE_META = [
    {
        "id": "implementation",
        "name": "実装・タスク分解",
        "lead_ai": "ChatGPT",
        "support_ais": ["Claude", "Grok"],
        "scorer_default": False,
    },
    {
        "id": "decision",
        "name": "意思決定支援",
        "lead_ai": "Claude",
        "support_ais": ["Gemini", "ChatGPT"],
        "scorer_default": True,
    },
    {
        "id": "logic_check",
        "name": "論理チェック",
        "lead_ai": "Claude",
        "support_ais": ["ChatGPT", "Gemini"],
        "scorer_default": True,
    },
    {
        "id": "research",
        "name": "情報収集・リサーチ設計",
        "lead_ai": "Grok",
        "support_ais": ["Gemini", "Claude"],
        "scorer_default": False,
    },
]
