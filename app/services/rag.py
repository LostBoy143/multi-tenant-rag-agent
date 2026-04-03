import logging
import uuid
from functools import partial

from anyio import to_thread
from google import genai
from google.genai.types import GenerateContentConfig
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

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

RESPONSE STYLE:
- Be conversational and natural. Sound like a knowledgeable, friendly human — \
not a search engine.
- Keep answers SHORT. 1-3 sentences for simple factual questions. Only go \
longer when the question genuinely requires detail (step-by-step guides, \
comparisons, explanations of complex topics).
- Match your answer length to the question complexity. "What is X?" needs a \
sentence or two, not five paragraphs.

STRICT RULES:
- NEVER say "based on the provided documents", "according to the context", \
"the documents mention", or anything that reveals you are reading from a \
knowledge base. Just state the answer naturally as your own knowledge.
- NEVER reference filenames, chunk numbers, or sources in your answer text. \
Source attribution is handled separately by the system.
- NEVER start your answer with "Based on...", "According to...", or \
"The provided information states...".
- If the context is insufficient to answer, say something brief and natural \
like "I don't have information on that — could you rephrase or ask something \
else?" Do NOT say "the documents don't contain" or similar.
- If the user sends a casual greeting (hi, hello, hey, etc.) or small talk, \
respond with a brief friendly greeting and offer to help. Ignore the context \
for greetings.
- If a question is ambiguous, give the best short answer you can and ask a \
brief clarifying question.
- Use bullet points or numbered lists ONLY when listing 3+ distinct items. \
Never use markdown headers (#) in responses.
- Do NOT repeat the question back to the user.
- Do NOT pad responses with filler phrases like "Great question!", \
"Sure, I'd be happy to help!", "That's a really interesting question!".
"""

NO_CONTEXT_INSTRUCTION = """\
You are a helpful chatbot on a company's website. The user asked a question \
but no relevant information was found in the knowledge base.

Respond briefly and naturally. Do NOT say "no documents found" or "the context \
is empty". Instead say something like "I don't have specific information on \
that. Could you try rephrasing, or is there something else I can help with?"

If the user's message is a greeting or small talk, just respond naturally.
"""

_llm_client: genai.Client | None = None


def _get_llm_client() -> genai.Client:
    global _llm_client
    if _llm_client is None:
        _llm_client = genai.Client(api_key=settings.gemini_api_key)
    return _llm_client


def _build_context_message(chunks: list[str]) -> str:
    numbered = [f"[{i + 1}] {text}" for i, text in enumerate(chunks)]
    return "KNOWLEDGE BASE:\n\n" + "\n\n".join(numbered)


def _sync_generate(system: str, user_message: str) -> str:
    client = _get_llm_client()
    response = client.models.generate_content(
        model=settings.llm_model,
        contents=user_message,
        config=GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            max_output_tokens=1024,
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
    # 1. Fetch Agent and its linked Knowledge Bases
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent)
            .options(selectinload(Agent.knowledge_bases))
            .where(Agent.id == agent_id, Agent.organization_id == organization_id)
        )
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise ValueError(f"Agent {agent_id} not found for organization {organization_id}")
            
        system_instruction = agent.system_prompt or DEFAULT_SYSTEM_INSTRUCTION
        kb_ids = [kb.id for kb in agent.knowledge_bases]

    # 2. Vector search (filtered by KB IDs)
    query_vector = await to_thread.run_sync(partial(embed_query, question))

    results = await search_chunks(
        qdrant, 
        organization_id, 
        query_vector, 
        knowledge_base_ids=kb_ids if kb_ids else None, 
        top_k=top_k
    )

    if not results:
        answer_text = await to_thread.run_sync(
            partial(_sync_generate, NO_CONTEXT_INSTRUCTION, question)
        )
        return QueryResponse(answer=answer_text, sources=[])

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

    answer_text = await to_thread.run_sync(
        partial(_sync_generate, system_instruction, user_message)
    )

    return QueryResponse(answer=answer_text, sources=sources)
