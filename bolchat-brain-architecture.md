# BolChat "Brain" Architecture & Memory System

BolChat uses a highly optimized, hybrid RAG (Retrieval-Augmented Generation) architecture to provide intelligent, contextual, and safe conversations while automatically capturing high-quality leads.

---

## 1. Short-Term Conversational Memory

LLMs are inherently stateless — they have zero memory between API calls. To give BolChat its natural conversational flow, we implement **Short-Term Memory** via a session transcript mechanism.

### How It Works
- **Conversation Tracking:** Every chat session is assigned a unique UUID (`conversation_id`). The widget creates this by calling `POST /api/v1/public/chat/session` when the user first opens the chat.
- **Message Persistence:** Every user message and bot reply is saved to the `messages` table in PostgreSQL, linked to the `conversation_id`.
- **Transcript Injection:** When a user sends a new message, the backend (`public.py`) retrieves ALL prior messages from that `conversation_id` and passes them as context to the LLM alongside the new question.
- **Context Awareness:** Because the AI sees the full history in its prompt, it understands context. For example, if it asks "What is your name?", and the user replies "Shubham", the AI recognizes "Shubham" is the answer to its previous question — not a random search query about someone named Shubham in the knowledge base.

### Anti-Hallucination Rule
We added a critical rule in the system prompt to prevent the AI from confusing user-provided contact details with knowledge base queries:
> *"CONTEXT AWARENESS: If the user is simply providing their name, email, or phone number in response to your previous question, DO NOT treat it as a question to be answered. Just thank them and confirm you have their details."*

---

## 2. Hybrid Sentiment & Intent Analysis (Lead Capture)

Our lead extraction pipeline uses a **Hybrid Architecture**, blending the intelligence of LLMs with the reliability of deterministic backend code. This approach ensures zero additional LLM API calls while maintaining high accuracy.

### Phase 1: LLM Sentiment Analysis (The Brain)
We instruct the LLM to dynamically analyze the user's intent during the conversation. If the LLM determines the user is showing high intent (asking about pricing, booking, shipping, etc.), it generates a structured, hidden JSON block at the end of its response:
```json
<lead>{"name": "John", "email": "john@example.com", "phone": "+1234567890", "interest": "Pricing"}</lead>
```
This block is invisible to the user — it gets stripped from the display text by a regex in `rag.py` before sending the response.

### Phase 2: Deterministic Extraction (The Safety Net)
LLMs can hallucinate. To prevent dirty data from entering the CRM:

1. **Anti-Hallucination Regex:** The backend (`lead_extractor.py`) runs a regex scan over the *user's raw messages* to verify that the email or phone number the AI claims to have captured was *actually typed by the user*. If the AI hallucinates a fake email, the backend instantly discards it.
2. **Fallback Intent Scanner:** If the AI fails to generate the `"interest"` key, or generates something invalid, the backend falls back to a hardcoded keyword dictionary. It scans the user's text for high-intent triggers like "discount", "demo", "booking", "shipping" and categorizes the lead automatically.
3. **Name Validation:** Names from the AI are only accepted if they are ≤80 characters, contain no digits, and are not placeholder values like "John Doe" or "null".

### Supported Intent Categories
The system recognizes intent signals for both B2B and B2C/E-commerce:
- **B2B:** Pricing, Demo, Trial, Enterprise, API, Integration, Plans, Schedule, Contact, Onboarding, CRM, Custom
- **E-commerce:** Discounts, Shipping, Orders, Returns, Checkout, Availability

---

## 3. Long-Term Memory (Persistent Visitor Profiles) — IMPLEMENTED

BolChat now has **Long-Term Memory**. If a visitor chats today, closes the browser, and returns days or weeks later, the bot remembers who they are and what they were interested in — without them ever logging in.

### Architecture

#### Step 1: Persistent Browser Identity (`widget.js`)
When the BolChat widget loads on a client's website for the first time, it generates a unique `visitor_id` using `crypto.randomUUID()` and stores it in the browser's `localStorage`. This ID persists across page refreshes, browser restarts, and return visits.

```javascript
// Persistent Visitor ID (Long-Term Memory)
const VISITOR_STORAGE_KEY = `bc_visitor_${AGENT_ID}`;
let visitorId = localStorage.getItem(VISITOR_STORAGE_KEY);
if (!visitorId) {
  visitorId = crypto.randomUUID();
  localStorage.setItem(VISITOR_STORAGE_KEY, visitorId);
}
```

The `visitor_id` is sent as an `X-Visitor-ID` HTTP header on every API call (session creation and chat queries).

#### Step 2: Profile Lookup (`public.py`)
When a chat query arrives, the backend checks if this `visitor_id` has any past lead records:

```python
past_lead_result = await db.execute(
    select(Lead)
    .where(
        Lead.visitor_id == visitor_id,
        Lead.organization_id == organization.id,
    )
    .order_by(desc(Lead.updated_at))
    .limit(1)
)
past_lead = past_lead_result.scalar_one_or_none()
```

If a lead is found with a name or email, a `visitor_profile` dictionary is constructed and passed to the RAG engine.

#### Step 3: Prompt Injection (`rag.py`)
If a `visitor_profile` exists, the RAG engine secretly injects a memory note into the AI's system prompt:

```
RETURNING VISITOR (LONG-TERM MEMORY):
This person has visited before. Their name is Shubham.
Their email is shubham@example.com.
Previously they were interested in: Pricing.
Welcome them back by name if you know it, and ask how you can help today.
Do NOT re-ask for contact details you already have.
Do NOT mention that you have a 'memory' or 'database' — just be naturally welcoming.
```

This injection happens for both regular queries AND greetings. So even if a returning visitor just says "hi", the bot responds with: *"Welcome back, Shubham! How can I help you today?"*

#### Step 4: Data Persistence (`lead_extractor.py`)
When a lead is captured, the `visitor_id` is saved alongside it in the `leads` table. This creates the link between the anonymous browser fingerprint and the captured contact details.

### Database Schema Change
A new indexed column was added to the `leads` table:
```sql
ALTER TABLE leads ADD COLUMN visitor_id VARCHAR(64);
CREATE INDEX ix_leads_visitor_id ON leads (visitor_id);
```

### Privacy & Security Notes
- The `visitor_id` is a random UUID — it contains no personally identifiable information.
- It is scoped per-agent (`bc_visitor_${AGENT_ID}`), so different BolChat widgets on different websites maintain separate identities.
- Users can clear their localStorage at any time to reset their identity.
- The system never tells the user it has a "memory" or "database" — it just feels naturally welcoming.

---

## 4. Complete Data Flow Summary

```
User opens chat widget
    ↓
Widget checks localStorage for visitor_id
    ↓ (if not found, generates one)
Widget calls POST /chat/session with X-Visitor-ID header
    ↓
User sends a message
    ↓
Widget calls POST /chat/query with X-Visitor-ID + X-Conversation-ID headers
    ↓
Backend looks up Lead table by visitor_id → builds visitor_profile
    ↓
RAG engine injects visitor_profile + lead capture prompt into system instructions
    ↓
LLM generates response (with hidden <lead> block if contact info detected)
    ↓
Backend strips <lead> block from display text
    ↓
Backend validates extracted fields via regex (anti-hallucination)
    ↓
Lead is upserted into PostgreSQL with visitor_id attached
    ↓
Clean response sent to user
```

---

## 5. Files Modified

| File | Role |
|------|------|
| `rag/static/widget.js` | Generates persistent `visitor_id`, sends `X-Visitor-ID` header |
| `rag/app/models/lead.py` | Added `visitor_id` column to Lead model |
| `rag/app/routers/public.py` | Reads `X-Visitor-ID`, queries past leads, passes profile to RAG |
| `rag/app/services/rag.py` | Injects visitor memory into system prompt (including greetings) |
| `rag/app/services/lead_extractor.py` | Saves `visitor_id` on new lead rows |
| `rag/alembic/versions/5028a566fb75_*.py` | Database migration for `visitor_id` column |
