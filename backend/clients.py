import asyncio
import logging
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# デフォルトモデル
DEFAULT_CLAUDE = "claude-haiku-4-5-20251001"
DEFAULT_CHATGPT = "gpt-5.4-mini"
DEFAULT_GEMINI = "gemini-2.5-flash"
DEFAULT_GROK = "grok-4-1-fast"


async def call_claude(prompt: str, max_tokens: int, language: str, model: str, api_key: str = "") -> str:
    """Claude API を呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("Anthropic API キーが設定されていません")
    if not model:
        model = DEFAULT_CLAUDE
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
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """OpenAI GPT API を呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("OpenAI API キーが設定されていません")
    if not model:
        model = DEFAULT_CHATGPT
    client = AsyncOpenAI(api_key=api_key)

    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            # gpt-5系など一部モデルで content が None になる場合がある
            if content is None:
                logger.warning(
                    f"ChatGPT ({model}) の content が None。"
                    f" finish_reason={response.choices[0].finish_reason}"
                )
                content = ""
            return content
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"ChatGPT リトライ {attempt + 1}/2: {e}。{wait}秒後に再試行")
            await asyncio.sleep(wait)


async def call_gemini(
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """Google Gemini API を google-genai SDK で呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("Gemini API キーが設定されていません")
    if not model:
        model = DEFAULT_GEMINI
    client = genai.Client(api_key=api_key)
    # gemini-2.5-flash の出力上限は8192トークン
    capped_tokens = min(max_tokens, 8192)

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
    prompt: str, max_tokens: int, language: str, model: str, api_key: str = ""
) -> str:
    """Grok API を OpenAI 互換クライアントで呼び出す。api_key が空の場合は ValueError を raise。"""
    if not api_key:
        raise ValueError("Grok API キーが設定されていません")
    if not model:
        model = DEFAULT_GROK
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
