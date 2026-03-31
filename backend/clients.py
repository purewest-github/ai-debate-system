import asyncio
import logging
import os
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

import os as _os

def _default_claude()  -> str: return _os.getenv("DEFAULT_MODEL_CLAUDE",  "claude-opus-4-5")
def _default_chatgpt() -> str: return _os.getenv("DEFAULT_MODEL_CHATGPT", "gpt-4o")
def _default_gemini()  -> str: return _os.getenv("DEFAULT_MODEL_GEMINI",  "gemini-2.5-flash")
def _default_grok()    -> str: return _os.getenv("DEFAULT_MODEL_GROK",    "grok-3-mini")


async def call_claude(
    prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = ""
) -> str:
    """Claude API を呼び出す。api_key 未指定時は ANTHROPIC_API_KEY 環境変数を使用。"""
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API キーが設定されていません")
    if not model:
        model = _default_claude()
    client = AsyncAnthropic(api_key=api_key)

    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"Claude リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_chatgpt(
    prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = ""
) -> str:
    """OpenAI GPT API を呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("OpenAI API キーが設定されていません")
    if not model:
        model = _default_chatgpt()
    client = AsyncOpenAI(api_key=api_key)

    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            # reasoning モデルでは content が空になり reasoning_content に入る場合がある
            if not content:
                content = getattr(response.choices[0].message, "reasoning_content", "") or ""
                if not content:
                    logger.warning(
                        f"ChatGPT ({model}) の content が空。"
                        f" finish_reason={response.choices[0].finish_reason}"
                    )
            return content
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"ChatGPT リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_gemini(
    prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = ""
) -> str:
    """Google Gemini API を google-genai SDK で呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("Gemini API キーが設定されていません")
    if not model:
        model = _default_gemini()
    client = genai.Client(api_key=api_key)
    # 安定した完全レスポンスを優先するため4096でキャップ
    capped_tokens = min(max_tokens, 4096)

    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(max_output_tokens=capped_tokens),
            )
            return response.text
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"Gemini リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_grok(
    prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = ""
) -> str:
    """Grok API を OpenAI 互換クライアントで呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("Grok API キーが設定されていません")
    if not model:
        model = _default_grok()
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"Grok リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)
