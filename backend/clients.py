import asyncio
import os
import logging
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# デフォルトモデル
DEFAULT_CLAUDE = "claude-opus-4-5"
DEFAULT_CHATGPT = "gpt-4o"
DEFAULT_GEMINI = "gemini-2.0-flash"
DEFAULT_GROK = "grok-2-1212"


async def call_claude(prompt: str, max_tokens: int, language: str, model: str) -> str:
    """Claude API を呼び出す。ANTHROPIC_API_KEY は環境変数から取得。"""
    if not model:
        model = DEFAULT_CLAUDE
    client = AsyncAnthropic()

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
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """OpenAI GPT API を呼び出す。"""
    if not model:
        model = DEFAULT_CHATGPT
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    client = AsyncOpenAI(api_key=key)

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
            logger.warning(f"ChatGPT リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_gemini(
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """Google Gemini API を google-genai SDK で呼び出す。"""
    if not model:
        model = DEFAULT_GEMINI
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=key)

    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            return response.text
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"Gemini リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_grok(
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """Grok API を OpenAI 互換クライアントで呼び出す。"""
    if not model:
        model = DEFAULT_GROK
    key = api_key or os.environ.get("GROK_API_KEY", "")
    client = AsyncOpenAI(api_key=key, base_url="https://api.x.ai/v1")

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
