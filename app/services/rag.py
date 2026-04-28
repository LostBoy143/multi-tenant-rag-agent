import logging
import re
import time
import uuid
from functools import partial

from anyio import to_thread
import groq
from google import genai
from google.genai.types import GenerateContentConfig
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent
from app.models.lead import Lead
from app.schemas.chat import QueryResponse, SourceChunk
from app.services.embedding import embed_query
from app.services.vector_store import search_chunks

logger = logging.getLogger(__name__)

# ── Lead-capture prompt fragments (§4.2) ─────────────────────────────────────

_LEAD_CAPTURE_PASSIVE = """\

LEAD CAPTURE (PASSIVE MODE):
- Do NOT proactively ask for contact information.
- If the user voluntarily shares their name, email, phone, or company name, \
acknowledge it naturally and continue helping.
- When you have confirmed contact details from the user's own messages, append \
EXACTLY ONE machine-parseable block at the very end of your reply (after your \
visible answer, on its own line):
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Support"}</lead>
- Omit any keys you don't know (e.g., if you only know email, output <lead>{"email":"john@example.com"}</lead>). 
- Identify the user's primary intent in 1-2 words (e.g. "Pricing", "Demo", "Shipping") and include it as the "interest" key. NEVER fabricate contact info."""

_LEAD_CAPTURE_SMART = """\

LEAD CAPTURE (SMART MODE):
- Be fully helpful first. Do not ask for contact info on an opening "hi".
- After a visitor signals genuine interest (pricing, demo, product details, etc.), you may naturally offer to follow up. 
- Keep your request to ONE extremely short conversational sentence. E.g.: "Happy to send you more details — what's the best email to reach you?"
- DO NOT repeat requests for information you already have. If you already know their name, don't ask for it again.
- If you have their name and email, you can ask for a phone number or just say you'll reach out.
- ALWAYS answer the user's question FIRST before asking for contact info.
- When the user shares contact details, append EXACTLY ONE block at the end of your reply:
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Demo"}</lead>
- Omit any keys you don't know. Include an "interest" key summarizing their goal (e.g. "Pricing", "Support")."""

_LEAD_CAPTURE_AGGRESSIVE = """\

LEAD CAPTURE (PROACTIVE MODE):
- After your FIRST substantive answer (not a greeting), ask the user for their contact info in ONE very short sentence.
- E.g.: "Before I dive deeper, what's your name and the best email to follow up?" 
- DO NOT repeat requests for information you already have. If you know their name, just ask for email/phone.
- ALWAYS answer the user's specific question FIRST before pivoting to lead capture.
- If the user asks a question about lead capture (e.g. "do u need email too?"), answer it directly and warmly.
- When the user shares contact details, append EXACTLY ONE block at the end of your reply:
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Pricing"}</lead>
- Omit any keys you don't know. Include an "interest" key."""

_LEAD_MODE_PROMPTS: dict[str, str] = {
    "passive": _LEAD_CAPTURE_PASSIVE,
    "smart": _LEAD_CAPTURE_SMART,
    "aggressive": _LEAD_CAPTURE_AGGRESSIVE,
}

_LEAD_BLOCK_RE = re.compile(r"<lead>.*?</lead>", re.DOTALL | re.IGNORECASE)


def _strip_lead_block(text: str) -> str:
    """Remove <lead>…</lead> from the display text sent to visitors."""
    return _LEAD_BLOCK_RE.sub("", text).strip()

DEFAULT_SYSTEM_INSTRUCTION = """\
You are a helpful AI assistant named {agent_name} embedded on a company's website. You answer visitor \
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
- CONTEXT AWARENESS: If the user is simply providing their name, email, or phone number in response to your previous question, DO NOT treat it as a question to be answered. Just thank them, confirm you have their details, and politely tell them someone will reach out. Do NOT use the knowledge base to try and explain who they are.
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


# ── Contact-reply detection ───────────────────────────────────────────────────

_CONTACT_ASK_SIGNALS = (
    "name", "email", "phone", "number", "contact", "reach you",
    "follow up", "get back to you", "details",
)

_EMAIL_RE_SIMPLE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE_SIMPLE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")


def _is_contact_reply(user_text: str, last_bot_message: str | None) -> bool:
    """
    Detect if the user is simply providing contact info (name, email, phone)
    in response to the bot's previous question asking for it.
    Returns True to signal: skip vector search, use acknowledgment prompt.
    """
    if not last_bot_message:
        return False

    # Check if the bot's last message was asking for contact info
    bot_lower = last_bot_message.lower()
    bot_asked_for_contact = any(signal in bot_lower for signal in _CONTACT_ASK_SIGNALS)
    if not bot_asked_for_contact:
        return False

    user_clean = user_text.strip()
    words = user_clean.split()

    # If it's an email or phone, it's definitely contact info
    if _EMAIL_RE_SIMPLE.search(user_clean) or _PHONE_RE_SIMPLE.search(user_clean):
        return True

    # Short text (1-4 words), no question mark → likely a name
    if len(words) <= 4 and "?" not in user_clean:
        return True

    return False


CONTACT_ACK_INSTRUCTION = """\
You are a friendly AI assistant named {agent_name} on a company's website. The user just provided their \
contact information (like their name, email, or phone number) in response to your \
previous question. Acknowledge it warmly in ONE short sentence. If they only gave \
partial info (e.g. just a name), ask for the remaining details (email or phone) \
naturally. Do NOT use markdown. Do NOT look up anything about this person. \
Just acknowledge and continue collecting their info.
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


def _sync_generate(
    system: str,
    user_message: str,
    temperature: float = 0.4,
    max_output_tokens: int = 1024,
) -> str:
    # 1. Attempt Groq First
    try:
        if not settings.groq_api_key:
            raise ValueError("Groq API key not found in environment.")
            
        groq_client = groq.Client(api_key=settings.groq_api_key)
        completion = groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message}
            ],
            temperature=temperature,
            max_completion_tokens=max_output_tokens,
        )
        logger.info("Response successfully generated by Groq.")
        return completion.choices[0].message.content or "Sorry, I wasn't able to process that. Could you try again?"

    # 2. Reroute to Gemini if Groq fails
    except Exception as groq_e:
        logger.warning(f"Groq API failed with error: {groq_e}. Falling back to Gemini.")
        
        try:
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
            logger.info("Response successfully generated by Gemini (Fallback).")
            return response.text or "Sorry, I wasn't able to process that. Could you try again?"
            
        except genai.errors.APIError as gemini_e:
            logger.error(f"Gemini fallback also failed: {gemini_e}")
            raise gemini_e


async def answer_query(
    qdrant: AsyncQdrantClient,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    question: str,
    top_k: int = 5,
    visitor_profile: dict | None = None,
    last_bot_message: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> tuple[QueryResponse, str]:
    """
    Returns (QueryResponse, raw_answer_text).
    QueryResponse.answer is the CLEAN display text (lead block stripped).
    raw_answer_text is the full model output including any <lead> block.
    """
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
                DEFAULT_SYSTEM_INSTRUCTION.format(agent_name=agent.name)
                + "\n\nADDITIONAL INSTRUCTIONS FROM THE AGENT OWNER:\n"
                + agent.system_prompt
            )
        else:
            system_instruction = DEFAULT_SYSTEM_INSTRUCTION.format(agent_name=agent.name)
            
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

    # 5. Inject lead capture system prompt injection
    lead_capture_enabled = bool(agent_settings.get("lead_capture_enabled", False))
    lead_capture_mode = agent_settings.get("lead_capture_mode", "smart")
    lead_prompt_fragment = ""
    if lead_capture_enabled and lead_capture_mode in _LEAD_MODE_PROMPTS:
        lead_prompt_fragment = _LEAD_MODE_PROMPTS[lead_capture_mode]
        system_instruction += lead_prompt_fragment

    # 6. Inject Current Conversation Lead State (so AI doesn't re-ask)
    if lead_capture_enabled and conversation_id:
        async with async_session_factory() as db_session:
            lead_res = await db_session.execute(
                select(Lead).where(Lead.conversation_id == conversation_id)
            )
            current_lead = lead_res.scalar_one_or_none()
            if current_lead:
                captured = []
                if current_lead.name: captured.append(f"Name: {current_lead.name}")
                if current_lead.email: captured.append(f"Email: {current_lead.email}")
                if current_lead.phone: captured.append(f"Phone: {current_lead.phone}")
                if captured:
                    system_instruction += (
                        f"\n\nCURRENT CONVERSATION STATE: You have already captured: {', '.join(captured)}. "
                        "Do NOT ask for these specific details again. Only ask for missing information."
                    )

    # 3. Inject long-term memory (returning visitor profile)
    if visitor_profile:
        parts = []
        if visitor_profile.get("name"):
            parts.append(f"Their name is {visitor_profile['name']}.")
        if visitor_profile.get("email"):
            parts.append(f"Their email is {visitor_profile['email']}.")
        if visitor_profile.get("interest"):
            parts.append(f"Previously they were interested in: {visitor_profile['interest']}.")
        if parts:
            memory_note = (
                "\n\nRETURNING VISITOR (LONG-TERM MEMORY): "
                "This person has visited before. " + " ".join(parts)
                + " Welcome them back by name if you know it, and ask how you can help today. "
                "Do NOT re-ask for contact details you already have. "
                "Do NOT mention that you have a 'memory' or 'database' — just be naturally welcoming."
            )
            system_instruction += memory_note

    # 4. Short-circuit for greetings -- no vector search needed
    if _is_greeting(question):
        t0 = time.perf_counter()
        # For returning visitors, use memory-enhanced greeting; otherwise plain greeting
        greeting_system = GREETING_INSTRUCTION.format(agent_name=agent.name) + lang_instruction
        if visitor_profile and visitor_profile.get("name"):
            greeting_system += (
                f"\n\nIMPORTANT: This is a returning visitor named {visitor_profile['name']}. "
                "Welcome them back by name warmly in ONE short sentence and ask how you can help today. "
                "Do NOT mention databases, memory, or systems."
            )
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, greeting_system, question, temperature, max_tokens)
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        clean_answer = _strip_lead_block(raw_answer)
        return QueryResponse(answer=clean_answer, sources=[], response_time_ms=elapsed_ms), raw_answer

    # 5. Short-circuit for contact info replies — skip vector search entirely
    if lead_capture_enabled and _is_contact_reply(question, last_bot_message):
        t0 = time.perf_counter()
        contact_system = CONTACT_ACK_INSTRUCTION.format(agent_name=agent.name) + lang_instruction
        if lead_capture_mode in _LEAD_MODE_PROMPTS:
            contact_system += _LEAD_MODE_PROMPTS[lead_capture_mode]
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, contact_system, f"Bot's previous message: {last_bot_message}\n\nUser's reply: {question}", temperature, max_tokens)
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        clean_answer = _strip_lead_block(raw_answer)
        return QueryResponse(answer=clean_answer, sources=[], response_time_ms=elapsed_ms), raw_answer

    # 6. Vector search (all org documents)
    query_vector = await to_thread.run_sync(partial(embed_query, question))

    results = await search_chunks(
        qdrant,
        organization_id,
        query_vector,
        top_k=top_k,
    )

    if not results:
        t0 = time.perf_counter()
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, NO_CONTEXT_INSTRUCTION + lang_instruction, question, temperature, max_tokens)
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        clean_answer = _strip_lead_block(raw_answer)
        return QueryResponse(answer=clean_answer, sources=[], response_time_ms=elapsed_ms), raw_answer

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
    raw_answer = await to_thread.run_sync(
        partial(_sync_generate, system_instruction, user_message, temperature, max_tokens)
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    clean_answer = _strip_lead_block(raw_answer)
    return QueryResponse(answer=clean_answer, sources=sources, response_time_ms=elapsed_ms), raw_answer
