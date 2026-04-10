import logging
import time
import uuid
from functools import partial

from anyio import to_thread
from google import genai
from google.genai.types import GenerateContentConfig
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent
from app.schemas.chat import QueryResponse, SourceChunk
from app.services.embedding import embed_query
from app.services.vector_store import search_chunks

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_INSTRUCTION = """\
You are a helpful chatbot embedded on a company's website. You answer visitor \
questions using the company's internal knowledge base provided below as context.

PERSONALITY:
You are a friendly, knowledgeable human who works at this company. You speak \
naturally like a real person in a chat — casual, warm, concise. Imagine you're \
texting a customer who asked a quick question. You don't lecture. You don't \
dump information. You answer the specific question and stop.

RESPONSE LENGTH — THIS IS CRITICAL:
- Default to 1-3 sentences. That's it. Most questions need ONE short paragraph.
- "What does he do?" → one sentence answer, maybe two.
- "Tell me about your services" → 2-3 sentences max.
- ONLY write more than 3 sentences if the user explicitly asks for detail, \
a full list, a step-by-step guide, or a comparison.
- When in doubt, be SHORTER not longer. You can always say more if they ask.

FORMATTING — THIS IS CRITICAL:
- Write in plain text. Do NOT use markdown. No ** bold **, no * italics *, \
no bullet points (- or *), no numbered lists, no headers (#).
- Write flowing sentences and short paragraphs like a human in a chat would.
- If you need to mention multiple things, weave them into a natural sentence \
like "He works with React, Next.js, and Node.js" — NOT a bulleted list.

STRICT RULES:
- NEVER reveal you are reading from a knowledge base or documents. No \
"based on the provided documents", "according to the context", etc. Just \
state things naturally as if you know them.
- NEVER reference filenames, chunk numbers, or sources.
- If the context doesn't have the answer, say something brief like "I'm not \
sure about that — anything else I can help with?"
- If the question is ambiguous, give a short best-guess answer and ask a \
brief follow-up.
- Do NOT repeat the question back to the user.
- Do NOT use filler phrases like "Great question!" or "Sure, I'd be happy \
to help!"
- Do NOT start with "So, ..." or "Well, ..." — just answer directly.
"""

NO_CONTEXT_INSTRUCTION = """\
You are a friendly chatbot on a company's website. The user asked something \
you don't have information about. Respond in 1 sentence to let them know \
you aren't sure, and offer further help. \
Do NOT say "no documents found" or anything about a knowledge base. \
Keep it casual and human. No markdown formatting.
"""

GREETING_INSTRUCTION = """\
You are a friendly chatbot on a company's website. The user just said hi or \
something casual. Reply with a brief, warm 1-sentence greeting and offer to \
help. Do NOT provide any information \
about the company. Do NOT use markdown. Just be friendly and short.
"""

_GREETING_PATTERNS = frozenset({
    "hi", "hello", "hey", "hii", "hiii", "yo", "sup", "hola",
    "howdy", "heya", "greetings", "good morning", "good afternoon",
    "good evening", "good day", "gm", "morning", "evening",
    "whats up", "what's up", "wassup", "wazzup",
    "how are you", "how r u", "how are u",
    "thanks", "thank you", "thankyou", "thx", "ty",
    "bye", "goodbye", "see you", "see ya", "cya",
    "ok", "okay", "k", "cool", "nice", "great",
})


def _is_greeting(text: str) -> bool:
    cleaned = text.lower().strip().rstrip("!?.,:;")
    if cleaned in _GREETING_PATTERNS:
        return True
    if len(cleaned.split()) <= 3 and any(cleaned.startswith(g) for g in ("hi", "hey", "hello", "yo", "good")):
        return True
    return False


_llm_client: genai.Client | None = None


def _get_llm_client() -> genai.Client:
    global _llm_client
    if _llm_client is None:
        _llm_client = genai.Client(api_key=settings.gemini_api_key)
    return _llm_client


def _build_context_message(chunks: list[str]) -> str:
    numbered = [f"[{i + 1}] {text}" for i, text in enumerate(chunks)]
    return "KNOWLEDGE BASE:\n\n" + "\n\n".join(numbered)


def _sync_generate(
    system: str,
    user_message: str,
    temperature: float = 0.4,
    max_output_tokens: int = 1024,
) -> str:
    client = _get_llm_client()
    response = client.models.generate_content(
        model=settings.llm_model,
        contents=user_message,
        config=GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    return response.text or "Sorry, I wasn't able to process that. Could you try again?"


async def answer_query(
    qdrant: AsyncQdrantClient,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    question: str,
    top_k: int = 5,
) -> QueryResponse:
    # 1. Fetch Agent
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent)
            .where(Agent.id == agent_id, Agent.organization_id == organization_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found for organization {organization_id}")

        if agent.system_prompt:
            system_instruction = (
                DEFAULT_SYSTEM_INSTRUCTION
                + "\n\nADDITIONAL INSTRUCTIONS FROM THE AGENT OWNER:\n"
                + agent.system_prompt
            )
        else:
            system_instruction = DEFAULT_SYSTEM_INSTRUCTION
        agent_settings = agent.settings or {}

    temperature = float(agent_settings.get("temperature", 0.4))
    max_tokens = int(agent_settings.get("max_tokens", 1024))

    # Append language guidance to the system instructions
    lang_code = agent_settings.get("language")
    lang_instruction = ""
    if lang_code and lang_code != "en":
        langs = {
            "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
            "zh": "Chinese", "ja": "Japanese", "ar": "Arabic", "ru": "Russian",
            "hi": "Hindi", "bn": "Bengali", "te": "Telugu", "mr": "Marathi", "ta": "Tamil",
            "ur": "Urdu", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi"
        }
        lang_name = langs.get(lang_code, lang_code)
        lang_instruction = f"\n\nCRITICAL LANGUAGE INSTRUCTION: You MUST identify the language the user is speaking and reply in that exact same language. However, if the user's text is gibberish, ambiguous, or unrecognizable, your absolute fallback language is {lang_name}. Do NOT fallback to English or any other language."
        system_instruction += lang_instruction

    # 2. Short-circuit for greetings -- no vector search needed
    if _is_greeting(question):
        t0 = time.perf_counter()
        answer_text = await to_thread.run_sync(
            partial(_sync_generate, GREETING_INSTRUCTION + lang_instruction, question, temperature, max_tokens)
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return QueryResponse(answer=answer_text, sources=[], response_time_ms=elapsed_ms)

    # 3. Vector search (all org documents)
    query_vector = await to_thread.run_sync(partial(embed_query, question))

    results = await search_chunks(
        qdrant,
        organization_id,
        query_vector,
        top_k=top_k,
    )

    if not results:
        t0 = time.perf_counter()
        answer_text = await to_thread.run_sync(
            partial(_sync_generate, NO_CONTEXT_INSTRUCTION + lang_instruction, question, temperature, max_tokens)
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return QueryResponse(answer=answer_text, sources=[], response_time_ms=elapsed_ms)

    sources: list[SourceChunk] = []
    context_texts: list[str] = []
    for point in results:
        payload = point.payload or {}
        text = payload.get("text", "")
        filename = payload.get("filename", "unknown")
        chunk_index = payload.get("chunk_index", 0)
        score = point.score if point.score is not None else 0.0

        context_texts.append(text)
        sources.append(
            SourceChunk(
                filename=filename,
                chunk_index=chunk_index,
                text_snippet=text[:200],
                score=round(score, 4),
            )
        )

    context_message = _build_context_message(context_texts)
    user_message = f"{context_message}\n\nUSER QUESTION: {question}"

    t0 = time.perf_counter()
    answer_text = await to_thread.run_sync(
        partial(_sync_generate, system_instruction, user_message, temperature, max_tokens)
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return QueryResponse(answer=answer_text, sources=sources, response_time_ms=elapsed_ms)
