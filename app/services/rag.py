import logging
import re
import time
import uuid
from functools import partial

from anyio import to_thread
import groq
from google import genai
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


class LLMProviderError(RuntimeError):
    """Raised when every configured LLM provider fails for one generation."""

# ── Lead-capture prompt fragments (§4.2) ─────────────────────────────────────

_LEAD_CAPTURE_PASSIVE = """\

LEAD CAPTURE (PASSIVE MODE):
- Do NOT proactively ask for contact information.
- If the user voluntarily shares their name, email, phone, or company name, \
acknowledge it naturally and continue helping.
- IMPORTANT: If the user says "no", "I don't want to share", "skip", or any clear refusal, \
immediately drop the topic and NEVER ask for their contact info again in this conversation.
- When you have confirmed contact details from the user's own messages, append \
EXACTLY ONE machine-parseable block at the very end of your reply (after your \
visible answer, on its own line):
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Support"}</lead>
- Omit any keys you don't know (e.g., if you only know email, output <lead>{"email":"john@example.com"}</lead>). 
- IMPORTANT: Always include ALL known contact details (name, email, phone) in the JSON block every time you emit it, even if you already emitted them in a previous turn.
- Identify the user's primary intent in 1-2 words (e.g. "Pricing", "Demo", "Shipping") and include it as the "interest" key. NEVER fabricate contact info."""

_LEAD_CAPTURE_SMART = """\

LEAD CAPTURE (SMART MODE):
- Be fully helpful first. Do NOT ask for contact info on a casual greeting (like "hi" or "just hanging around").
- ONLY offer to follow up or ask for contact info if the user explicitly asks about pricing, buying, or a demo. Do NOT ask on every message.
- Keep your request to ONE extremely short conversational sentence.
- DO NOT repeat requests for information you already have. If you already know their name, don't ask for it again.
- ALWAYS answer the user's question FIRST before asking for contact info.
- CRITICAL: If the user says "no", "I don't want a demo", "nah", "skip", "already shared", or any refusal — IMMEDIATELY drop it. NEVER ask for a demo or contact info again in ANY subsequent message. Just say "No problem" and move on naturally.
- When the user shares contact details, append EXACTLY ONE block at the end of your reply:
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Demo"}</lead>
- Omit any keys you don't know. 
- IMPORTANT: Always include ALL known contact details (name, email, phone) in the JSON block every time you emit it, even if you already emitted them in a previous turn.
- Include an "interest" key summarizing their goal (e.g. "Pricing", "Support")."""

_LEAD_CAPTURE_AGGRESSIVE = """\

LEAD CAPTURE (PROACTIVE MODE):
- After your FIRST substantive answer (not a greeting or casual chat like "hanging around"), ask the user for their contact info in ONE very short sentence using a contextual hook.
- E.g.: "I'd love to share more details on that — where is the best place to reach you?"
- DO NOT repeat requests for information you already have. If you know their name, just ask for email or phone.
- ALWAYS answer the user's specific question FIRST before pivoting to lead capture.
- If the user asks a question about lead capture (e.g. "do u need email too?"), answer it directly and warmly.
- CRITICAL: If the user says "no", "nah", "I already shared", "I'm not sharing", or any clear refusal — immediately acknowledge and NEVER ask for contact info or a demo again in this conversation. Do not loop. Move on to helping them.
- When the user shares contact details, append EXACTLY ONE block at the end of your reply:
  <lead>{"name":"John Doe","email":"john@example.com","phone":"+1234567890","interest":"Pricing"}</lead>
- Omit any keys you don't know. 
- IMPORTANT: Always include ALL known contact details (name, email, phone) in the JSON block every time you emit it, even if you already emitted them in a previous turn.
- Include an "interest" key."""

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

MEMORY & CONTEXT PRIORITY:
1. Current User Message (Highest Priority - ALWAYS address this first)
2. Recent Conversation History (Last few turns for context)
3. Known Visitor Data (Do NOT re-ask for contact info you already have)
4. Past Interest (Lowest Priority - Use only if highly relevant)

STRICT RULES:
- NEVER reveal you are an AI reading from a knowledge base or documents. Do NOT use phrases like "based on the provided documents", "according to the context", "in the knowledge base", etc. Just state things naturally.
- NEVER mention the words "knowledge base", "documents", or "context".
- If the user corrects you or provides new information (e.g., "I heard X is the founder"), just politely agree or confirm. Do NOT apologize profusely, and NEVER say "I should have known that" or reference your instructions or knowledge base.
- CONTEXT AWARENESS: If the user is simply providing their name, email, or phone number in response to your previous question, DO NOT treat it as a question to be answered. Just thank them, confirm you have their details, and politely tell them someone will reach out. Do NOT use the knowledge base to try and explain who they are.
- You MAY provide the company's contact information if it is highly relevant to the user's intent. However, DO NOT spam or repeatedly append the contact info to every message. Once you've shared it, don't keep repeating it.
- If the context doesn't have the answer, say something brief like "I'm not \
sure about that — anything else I can help with?"
- If the question is ambiguous, give a short best-guess answer and ask a \
brief follow-up.
- Do NOT repeat the question back to the user.
- Do NOT use filler phrases like "Great question!" or "Sure, I'd be happy \
to help!"
- Do NOT start with "So, ..." or "Well, ..." — just answer directly.
- NEVER claim to have done something you haven't done. For example, if a user \
says "note my name" or "take my number" but hasn't actually provided it yet, \
ASK them for it instead of saying "done" or "noted".
- NEVER fabricate or assume user details. If you don't know the user's name, \
email, or phone number, admit it honestly. Do not guess or invent information.
- If you shared the company's contact info once in this conversation, do NOT \
repeat it in subsequent messages unless the user explicitly asks for it again.
- NEVER invent or guess a company email address, phone number, or redirect the user to a fake department.
- If you do not know the answer, do NOT try to smoothly pivot into a sales pitch. Just admit you don't know.
"""

NO_CONTEXT_INSTRUCTION = """\
You are a friendly chatbot on a company's website. The user just asked a question that has nothing to do with this company, or a question you do not have the answer to.

CRITICAL RULES:
- You MUST respond in exactly ONE short sentence.
- You MUST politely state you do not know.
- NEVER invent or guess an email address, phone number, or company name.
- NEVER try to pivot, change the subject, or pitch a product.
- NEVER say "great question" or use any filler phrases.
- Do NOT say "no documents found" or mention a knowledge base.
- NEVER use markdown.

Examples of good responses:
- "I'm sorry, I don't have any information on that."
- "I'm just a company assistant, so I can't help with that one!"
- "I don't know the answer to that, sorry!"
- "I'm afraid I don't have details on that topic."
"""

GREETING_INSTRUCTION = """\
You are a friendly chatbot on a company's website. The user just said hi or something casual.

Reply with ONE short, warm sentence that offers to help. Be natural and conversational — like a real person, not a customer service script.

CRITICAL — NEVER use these overused robotic phrases (they are banned):
- "It's nice to meet you"
- "How can I assist you today"
- "How may I help you today"
- "Great to meet you"
- "Nice to meet you"
- "How can I help you today"
- Any variation of "It's a pleasure to..."

Instead, vary your tone. Some styles you can pick from (don't copy exactly, just use the spirit):
- "Hey! What can I do for you?"
- "Hi there! What brings you here today?"
- "Hey, what's up? Ask me anything."
- "Hello! What can I help you with?"
- "Hi! Got a question? I'm here."
- "Hey! What are you looking for today?"

Pick a style that feels fresh and genuine. NEVER repeat the same opener twice if there's prior conversation history. No markdown. Keep it to ONE sentence.
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

# Words that look like short replies but are NOT contact info being provided
_NON_CONTACT_SHORT_REPLIES = frozenset({
    "no", "nope", "nah", "yes", "ya", "yep", "sure", "ok", "okay", "k",
    "please", "connect", "thanks", "thank you", "ty", "thx",
    "maybe", "idk", "i don't know", "not really", "already", "bro",
    "ya sure", "yes sure", "okay sure", "please connect", "yes please",
})


def _is_contact_reply(user_text: str, last_bot_message: str | None) -> bool:
    """
    Detect if the user is actually providing contact info (email, phone, or a name)
    in response to the bot asking for it. Tightened to avoid false positives on
    short non-contact phrases like 'ya sure', 'no', 'please connect'.
    """
    if not last_bot_message:
        return False

    # Bot must have been asking for contact info
    bot_lower = last_bot_message.lower()
    if not any(signal in bot_lower for signal in _CONTACT_ASK_SIGNALS):
        return False

    user_clean = user_text.strip()
    user_lower = user_clean.lower()

    # Hard matches: email or phone number present → definitely contact info
    if _EMAIL_RE_SIMPLE.search(user_clean) or _PHONE_RE_SIMPLE.search(user_clean):
        return True

    # Skip obvious non-contact short phrases
    if user_lower in _NON_CONTACT_SHORT_REPLIES:
        return False
    # Multi-word phrases that start with negations or filler
    if user_lower.startswith(("no ", "yes ", "ya ", "please ", "i ", "not ", "bro", "already")):
        return False

    words = user_clean.split()
    # Short text (1-4 words), no question mark, not a refusal → likely a name
    if len(words) <= 4 and "?" not in user_clean:
        return True

    return False


CONTACT_ACK_INSTRUCTION = """\
You are a friendly AI assistant named {agent_name} on a company's website. The user just provided their \
contact information (like their name, email, or phone number) in response to your \
previous question. Acknowledge it warmly in ONE short sentence. If they only gave \
partial info (e.g. just a name), ask for the remaining details (email or phone) \
naturally. Do NOT use markdown. Do NOT look up anything about this person. \
Just acknowledge and continue collecting their info. NEVER share the company's internal fallback phone or email. \
NEVER claim you already have information that was not explicitly shared by the user in this conversation.
"""


_llm_client: genai.Client | None = None


def _get_llm_client() -> genai.Client:
    global _llm_client
    if _llm_client is None:
        _llm_client = genai.Client(
            api_key=settings.gemini_api_key, 
            http_options={"timeout": 45.0}
        )
    return _llm_client


def _build_context_message(chunks: list[str]) -> str:
    numbered = [f"[{i + 1}] {text}" for i, text in enumerate(chunks)]
    return "KNOWLEDGE BASE:\n\n" + "\n\n".join(numbered)


def _generate_with_gemini(system: str, messages: list[dict], temperature: float, max_output_tokens: int) -> str:
    client = _get_llm_client()
    from google.genai import types as genai_types
    gemini_contents = []
    for m in messages:
        gemini_role = "model" if m["role"] == "assistant" else "user"
        gemini_contents.append(
            genai_types.Content(
                role=gemini_role,
                parts=[genai_types.Part(text=m["content"])],
            )
        )
    response = client.models.generate_content(
        model=settings.llm_model,
        contents=gemini_contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    logger.info("Response successfully generated by Gemini.")
    return response.text or "Sorry, I wasn't able to process that. Could you try again?"


def _generate_with_groq(system: str, messages: list[dict], temperature: float, max_output_tokens: int) -> str:
    if not settings.groq_api_key:
        raise ValueError("Groq API key not configured for fallback.")

    groq_client = groq.Client(api_key=settings.groq_api_key)
    groq_messages = [{"role": "system", "content": system}] + messages
    completion = groq_client.chat.completions.create(
        model=settings.groq_model,
        messages=groq_messages,
        temperature=temperature,
        max_tokens=max_output_tokens,
        timeout=15.0,
    )
    logger.info("Response successfully generated by Groq.")
    return completion.choices[0].message.content or "Sorry, I wasn't able to process that. Could you try again?"


def _sync_generate(
    system: str,
    messages: list[dict],
    temperature: float = 0.4,
    max_output_tokens: int = 1024,
) -> str:
    """
    Generate a response using the primary LLM, falling back to the secondary.
    `messages` is the full multi-turn conversation list:
      [{"role": "user"|"assistant", "content": "..."}]
    The system prompt is prepended automatically.
    """
    providers = ["groq", "gemini"] if settings.primary_llm_provider.lower() == "groq" else ["gemini", "groq"]
    
    last_exception = None
    for provider in providers:
        try:
            if provider == "groq":
                return _generate_with_groq(system, messages, temperature, max_output_tokens)
            else:
                return _generate_with_gemini(system, messages, temperature, max_output_tokens)
        except Exception as e:
            logger.warning(f"{provider.capitalize()} API failed with error: {e}. Falling back...")
            last_exception = e
            
    logger.error(f"All LLM providers failed. Last exception: {last_exception}")
    if last_exception:
        raise LLMProviderError("All LLM providers failed.") from last_exception
    raise LLMProviderError("All LLM providers failed.")


async def answer_query(
    qdrant: AsyncQdrantClient,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    question: str,
    top_k: int = 5,
    visitor_profile: dict | None = None,
    last_bot_message: str | None = None,
    conversation_id: uuid.UUID | None = None,
    conversation_history: list[dict] | None = None,
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
        lang_instruction = f"""

CRITICAL LANGUAGE INSTRUCTION:
- Detect the user's language precisely.
- Respond ONLY in that language.
- Do NOT mix languages (e.g. no "Hinglish") under any circumstance.
- Maintain natural fluency like a native speaker.
- If the user's text is gibberish, ambiguous, or unrecognizable, your absolute fallback language is {lang_name}.
"""
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
        name_known = visitor_profile.get("name")
        email_known = visitor_profile.get("email")
        phone_known = visitor_profile.get("phone")
        interest_known = visitor_profile.get("interest")

        # Build a summary of what we already know about this visitor
        on_file = []
        if name_known: on_file.append(f"Name: {name_known}")
        if email_known: on_file.append(f"Email: {email_known}")
        if phone_known: on_file.append(f"Phone: {phone_known}")

        if lead_capture_enabled and on_file:
            # Returning visitor with lead data — use silently, never announce
            memory_note = (
                f"\n\nRETURNING VISITOR DATA (use silently — NEVER announce): "
                f"This visitor has interacted before. Details on file: {', '.join(on_file)}. "
                "STRICT RULES FOR RETURNING VISITORS: "
                "1. Do NOT re-ask for any of these details during lead capture. "
                "2. Do NOT proactively mention, confirm, or announce these details. "
                "Never say 'Welcome back [Name]' or 'I see you are [Name]' or "
                "'I have your details on file' unprompted. "
                "3. If the user provides updated contact info, accept it naturally. "
                "4. Only reference stored details if the USER explicitly asks "
                "(e.g. 'do you know my name?'). "
                "5. NEVER mention a 'database', 'records', 'memory', or 'file'."
            )
        else:
            # Visitor profile exists but no captured lead data yet.
            # Inject as a silent hint — bot knows prior interest but won't announce it.
            parts = []
            if name_known: parts.append(f"Their name is {name_known}.")
            if interest_known: parts.append(f"Previously they were interested in: {interest_known}.")
            memory_note = (
                "\n\nPREVIOUS VISITOR CONTEXT (use silently — NEVER announce): "
                + (" ".join(parts) if parts else "")
                + " STRICT RULES: "
                "1. Do NOT greet them by name unprompted. "
                "2. Do NOT mention you 'remember' them or their previous visits. "
                "3. Only use this info if the user brings it up or to avoid re-asking for info they already gave. "
                "4. NEVER mention a 'memory', 'database', or 'records'."
            )
        system_instruction += memory_note

    # 4. Short-circuit for greetings -- no vector search needed
    # Memory is NOT surfaced here — bot greets neutrally.
    # The visitor data will be used silently when the user actually does something.
    if _is_greeting(question):
        t0 = time.perf_counter()
        greeting_system = GREETING_INSTRUCTION.format(agent_name=agent.name) + lang_instruction
        hist = list(conversation_history or [])
        hist.append({"role": "user", "content": question})
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, greeting_system, hist, temperature, max_tokens)
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
        # Inject what's already been captured so the bot doesn't re-ask
        if conversation_id:
            async with async_session_factory() as db_cs:
                lead_cs_res = await db_cs.execute(
                    select(Lead).where(Lead.conversation_id == conversation_id)
                )
                current_lead_cs = lead_cs_res.scalar_one_or_none()
                if current_lead_cs:
                    captured_cs = []
                    if current_lead_cs.name: captured_cs.append(f"Name: {current_lead_cs.name}")
                    if current_lead_cs.email: captured_cs.append(f"Email: {current_lead_cs.email}")
                    if current_lead_cs.phone: captured_cs.append(f"Phone: {current_lead_cs.phone}")
                    if captured_cs:
                        contact_system += (
                            f"\n\nYOU ALREADY HAVE: {', '.join(captured_cs)}. "
                            "Do NOT ask for these again. Only ask for what is still missing."
                        )
        hist_c = list(conversation_history or [])
        hist_c.append({"role": "user", "content": question})
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, contact_system, hist_c, temperature, max_tokens)
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
        hist_nc = list(conversation_history or [])
        hist_nc.append({"role": "user", "content": question})
        raw_answer = await to_thread.run_sync(
            partial(_sync_generate, NO_CONTEXT_INSTRUCTION + lang_instruction, hist_nc, temperature, max_tokens)
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
    # Build the final user turn: inject KB context + current question
    final_user_turn = f"{context_message}\n\nUSER QUESTION: {question}"

    # Build multi-turn message list: all prior turns + the current enriched user turn
    hist_main = list(conversation_history or [])
    hist_main.append({"role": "user", "content": final_user_turn})

    t0 = time.perf_counter()
    raw_answer = await to_thread.run_sync(
        partial(_sync_generate, system_instruction, hist_main, temperature, max_tokens)
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    clean_answer = _strip_lead_block(raw_answer)
    return QueryResponse(answer=clean_answer, sources=sources, response_time_ms=elapsed_ms), raw_answer
