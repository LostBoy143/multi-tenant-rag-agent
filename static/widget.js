/* BolChat Widget v4.0 — Modern AI Agent Widget */
(() => {
  "use strict";

  const script = document.currentScript;
  if (!script) return;

  const API_KEY = script.getAttribute("data-key");
  const AGENT_ID = script.getAttribute("data-agent");
  const API_URL = script.getAttribute("data-api-url") || "https://api.bolchat.tech";

  if (!API_KEY || !AGENT_ID) {
    console.error("[BolChat] Missing data-key or data-agent on script tag.");
    return;
  }

  /* ── State ── */
  let isOpen = false;
  let sessionId = null;
  let isLoading = false;
  let shadowRoot = null;
  let messages = [];
  let teaserDismissed = false;
  let teaserTimer = null;
  let hasEnteredView = false;

  /* ── Persistent Visitor ID (Long-Term Memory) ── */
  const VISITOR_STORAGE_KEY = `bc_visitor_${AGENT_ID}`;
  let visitorId = localStorage.getItem(VISITOR_STORAGE_KEY);
  if (!visitorId) {
    visitorId = crypto.randomUUID ? crypto.randomUUID() : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    localStorage.setItem(VISITOR_STORAGE_KEY, visitorId);
  }

  let cfg = {
    agent_name: "BolChat AI",
    brand_color: "#ec4899",
    greeting: "Hi! How can I help you today?",
    position: "bottom-right",
    launcher_icon: "chat",
    launcher_text: "",
    launcher_shape: "circle",
    tooltip_text: "",
    chat_height: 560,
    /* v4 features — all OFF by default */
    teaser_text: "",
    glass_effect: false,
    gradient_enabled: false,
    attention_dot: false,
    entrance_animation: "none",
    suggested_replies: [],
  };

  /* ── Icon Library ── */
  const ICONS = {
    chat: '<svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>',
    bot: '<svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="11" rx="4"/><path d="M12 5V3"/><path d="M8.5 13h.01"/><path d="M15.5 13h.01"/></svg>',
    headphones: '<svg viewBox="0 0 24 24"><path d="M4 15v-3a8 8 0 0 1 16 0v3"/><path d="M6 14h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H6z"/><path d="M18 14h-1a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h1z"/></svg>',
    help: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 0 1 5.1 1.3c0 1.8-2.6 2.2-2.6 3.7"/><path d="M12 17h.01"/></svg>',
    zap: '<svg viewBox="0 0 24 24"><path d="m13 2-9 12h8l-1 8 9-12h-8z"/></svg>',
    brain: '<svg viewBox="0 0 24 24"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M19.938 10.5a4 4 0 0 1 .585.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M19.967 17.484A4 4 0 0 1 18 18"/></svg>',
    sparkles: '<svg viewBox="0 0 24 24"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg>',
    "message-circle": '<svg viewBox="0 0 24 24"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>',
    send: '<svg viewBox="0 0 24 24"><path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  };

  /* ── Helpers ── */
  function brand() { return cfg.brand_color || "#ec4899"; }
  function icon(name) { return ICONS[name] || ICONS.chat; }
  function html(s) { return { __html: s }; }
  function isLeft() { return cfg.position === "bottom_left" || cfg.position === "bottom-left"; }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.entries(attrs).forEach(([k, v]) => {
        if (v == null) return;
        if (k === "style" && typeof v === "object") Object.assign(node.style, v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else node.setAttribute(k, String(v));
      });
    }
    children.flat().forEach(c => {
      if (c == null) return;
      if (typeof c === "string") node.appendChild(document.createTextNode(c));
      else if (c.__html !== undefined) node.insertAdjacentHTML("beforeend", c.__html);
      else node.appendChild(c);
    });
    return node;
  }

  function reqHeaders() {
    const h = { "Content-Type": "application/json", "X-API-Key": API_KEY, "X-Agent-ID": AGENT_ID };
    if (visitorId) h["X-Visitor-ID"] = visitorId;
    return h;
  }

  /* ── CSS Builder ── */
  function buildCSS() {
    const h = Number(cfg.chat_height) || 560;
    return `
      :host {
        --bc-brand: ${brand()};
        --bc-text: #172033;
        --bc-muted: #667085;
        --bc-line: #e5e7eb;
        --bc-surface: #ffffff;
        --bc-soft: #f6f7fb;
        all: initial;
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      * { box-sizing: border-box; letter-spacing: 0; }
      button, input { font: inherit; }

      /* ═══════════════════ LAUNCHER ═══════════════════ */
      .bc-launcher {
        position: fixed;
        bottom: 22px;
        z-index: 2147483646;
        border: 0;
        color: #fff;
        background: var(--bc-brand);
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 0 18px 44px rgba(16,24,40,0.26);
        transition: transform 160ms ease, box-shadow 160ms ease;
      }
      .bc-launcher:hover {
        transform: translateY(-2px) scale(1.03);
        box-shadow: 0 22px 52px rgba(16,24,40,0.3);
      }
      .bc-launcher svg {
        width: 24px; height: 24px;
        fill: none; stroke: currentColor; stroke-width: 2;
        stroke-linecap: round; stroke-linejoin: round;
        flex-shrink: 0;
      }

      /* ── Shapes ── */
      .bc-shape-circle  { border-radius: 999px; width: 60px; height: 60px; }
      .bc-shape-rounded { border-radius: 16px;  width: 60px; height: 60px; }
      .bc-shape-square  { border-radius: 6px;   width: 60px; height: 60px; }
      .bc-shape-flower  { border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%; width: 62px; height: 62px; }
      .bc-shape-pill    { border-radius: 999px; height: 56px; min-width: 140px; padding: 0 24px; gap: 10px; }

      /* ── Launcher Text ── */
      .bc-launcher-text {
        font-size: 15px; font-weight: 700;
        white-space: nowrap; letter-spacing: -0.01em;
      }

      /* ── Glassmorphism ── */
      .bc-glass {
        background: color-mix(in srgb, var(--bc-brand) 65%, transparent) !important;
        backdrop-filter: blur(18px) saturate(1.6);
        -webkit-backdrop-filter: blur(18px) saturate(1.6);
        border: 1px solid rgba(255,255,255,0.25);
      }

      /* ── Animated Gradient ── */
      .bc-gradient {
        background: linear-gradient(
          135deg,
          var(--bc-brand),
          color-mix(in srgb, var(--bc-brand) 55%, #8b5cf6),
          var(--bc-brand)
        ) !important;
        background-size: 300% 300% !important;
        animation: bc-gradient-flow 5s ease infinite;
      }
      @keyframes bc-gradient-flow {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
      }

      /* ── Attention Dot ── */
      .bc-attention-dot {
        position: absolute;
        top: -2px; right: -2px;
        width: 14px; height: 14px;
        border-radius: 999px;
        background: #ef4444;
        border: 2.5px solid #fff;
        animation: bc-dot-pulse 2s ease infinite;
        pointer-events: none;
      }
      @keyframes bc-dot-pulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50%      { transform: scale(1.3); opacity: 0.7; }
      }

      /* ── Entrance Animations ── */
      .bc-enter-slide-up {
        animation: bc-slide-up 600ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
      }
      @keyframes bc-slide-up {
        from { opacity: 0; transform: translateY(40px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      .bc-enter-scale-in {
        animation: bc-scale-in 500ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
      }
      @keyframes bc-scale-in {
        from { opacity: 0; transform: scale(0.3); }
        to   { opacity: 1; transform: scale(1); }
      }
      .bc-enter-bounce-in {
        animation: bc-bounce-in 800ms cubic-bezier(0.68, -0.55, 0.27, 1.55) both;
      }
      @keyframes bc-bounce-in {
        0%   { opacity: 0; transform: translateY(60px) scale(0.5); }
        60%  { opacity: 1; transform: translateY(-8px) scale(1.05); }
        80%  { transform: translateY(3px) scale(0.98); }
        100% { transform: translateY(0) scale(1); }
      }

      /* ── Tooltip ── */
      .bc-tooltip-wrap { position: relative; }
      .bc-tooltip {
        position: absolute;
        bottom: calc(100% + 14px);
        padding: 8px 14px;
        background: #1e293b;
        color: #fff;
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        white-space: nowrap;
        pointer-events: none;
        opacity: 0;
        transition: opacity 200ms ease, transform 200ms ease;
        transform: translateY(4px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.15);
      }
      .bc-tooltip::after {
        content: '';
        position: absolute;
        top: 100%;
        border: 6px solid transparent;
        border-top-color: #1e293b;
      }
      .bc-tooltip-right { right: 0; }
      .bc-tooltip-right::after { right: 20px; }
      .bc-tooltip-left  { left: 0; }
      .bc-tooltip-left::after  { left: 20px; }
      .bc-tooltip-wrap:hover .bc-tooltip {
        opacity: 1;
        transform: translateY(0);
      }

      /* ── Teaser Message ── */
      .bc-teaser {
        position: fixed;
        bottom: 90px;
        z-index: 2147483645;
        max-width: 280px;
        padding: 14px 18px;
        background: #fff;
        color: #1e293b;
        font-size: 14px;
        font-weight: 500;
        line-height: 1.5;
        border-radius: 16px;
        border-bottom-right-radius: 4px;
        box-shadow: 0 12px 40px rgba(16,24,40,0.18), 0 0 0 1px rgba(15,23,42,0.06);
        cursor: pointer;
        animation: bc-teaser-in 500ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
        transition: opacity 300ms ease, transform 300ms ease;
      }
      .bc-teaser-left {
        border-bottom-right-radius: 16px;
        border-bottom-left-radius: 4px;
      }
      .bc-teaser.bc-teaser-out {
        opacity: 0;
        transform: translateY(8px) scale(0.95);
        pointer-events: none;
      }
      @keyframes bc-teaser-in {
        from { opacity: 0; transform: translateY(16px) scale(0.9); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
      }
      .bc-teaser-close {
        position: absolute;
        top: -6px;
        right: -6px;
        width: 20px; height: 20px;
        border-radius: 999px;
        background: #64748b;
        color: #fff;
        border: 2px solid #fff;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer;
        font-size: 11px;
        font-weight: bold;
        line-height: 1;
      }
      .bc-teaser-close:hover { background: #475569; }

      /* ═══════════════════ CHAT PANEL ═══════════════════ */
      .bc-panel {
        position: fixed;
        bottom: 94px;
        z-index: 2147483647;
        width: 390px;
        max-width: calc(100vw - 28px);
        height: ${h}px;
        max-height: calc(100vh - 118px);
        background: var(--bc-surface);
        border: 1px solid rgba(15,23,42,0.08);
        border-radius: 18px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        box-shadow: 0 26px 70px rgba(16,24,40,0.24);
        transform-origin: bottom right;
        transition: opacity 180ms ease, transform 180ms ease;
      }
      .bc-panel.bc-hidden  { opacity: 0; pointer-events: none; transform: translateY(14px) scale(0.97); }
      .bc-panel.bc-visible { opacity: 1; transform: translateY(0) scale(1); }

      .bc-header {
        min-height: 66px; padding: 14px;
        color: #fff;
        background: linear-gradient(135deg, var(--bc-brand), color-mix(in srgb, var(--bc-brand) 82%, #111827));
        display: flex; align-items: center; gap: 12px; flex-shrink: 0;
      }
      .bc-header-mark {
        width: 36px; height: 36px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.18);
        flex: 0 0 auto;
      }
      .bc-header-mark svg { width: 19px; height: 19px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
      .bc-title { min-width: 0; flex: 1; }
      .bc-title strong { display: block; font-size: 15px; line-height: 1.2; font-weight: 750; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .bc-status { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 11px; line-height: 1; color: rgba(255,255,255,0.82); }
      .bc-dot { width: 7px; height: 7px; border-radius: 999px; background: #34d399; box-shadow: 0 0 0 3px rgba(52,211,153,0.18); }

      .bc-close {
        width: 34px; height: 34px; border: 0; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; background: rgba(255,255,255,0.16); cursor: pointer; flex: 0 0 auto;
      }
      .bc-close:hover { background: rgba(255,255,255,0.26); }
      .bc-close svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }

      .bc-messages {
        min-height: 0; flex: 1; overflow-y: auto; padding: 18px 14px 16px;
        background: radial-gradient(circle at top left, color-mix(in srgb, var(--bc-brand) 10%, transparent), transparent 34%), var(--bc-soft);
        display: flex; flex-direction: column; gap: 12px;
        scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent;
      }
      .bc-row { display: flex; align-items: flex-end; gap: 8px; width: 100%; }
      .bc-row-user { justify-content: flex-end; }
      .bc-avatar {
        width: 26px; height: 26px; border-radius: 999px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; background: var(--bc-brand); flex: 0 0 auto;
        box-shadow: 0 6px 14px color-mix(in srgb, var(--bc-brand) 26%, transparent);
      }
      .bc-avatar svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
      .bc-bubble {
        max-width: min(78%, 286px); padding: 11px 13px; border-radius: 14px;
        font-size: 14px; line-height: 1.48; white-space: pre-wrap; overflow-wrap: anywhere;
        box-shadow: 0 1px 1px rgba(16,24,40,0.03);
      }
      .bc-bot .bc-bubble { color: var(--bc-text); background: #fff; border: 1px solid var(--bc-line); border-bottom-left-radius: 6px; }
      .bc-user .bc-bubble { color: #fff; background: var(--bc-brand); border-bottom-right-radius: 6px; }

      .bc-typing { display: flex; align-items: center; gap: 5px; padding: 4px 0; }
      .bc-typing span { width: 6px; height: 6px; border-radius: 999px; background: #94a3b8; animation: bc-bounce 1.1s infinite; }
      .bc-typing span:nth-child(2) { animation-delay: 120ms; }
      .bc-typing span:nth-child(3) { animation-delay: 240ms; }
      @keyframes bc-bounce {
        0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
        40% { transform: translateY(-4px); opacity: 1; }
      }

      /* ── Suggested Replies (above input, industry standard) ── */
      .bc-suggestions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 10px 12px 4px;
      }
      .bc-suggestion {
        padding: 8px 16px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
        color: var(--bc-text);
        background: linear-gradient(135deg, #f8fafc, #f1f5f9);
        border: 1px solid #e2e8f0;
        cursor: pointer;
        transition: all 200ms cubic-bezier(0.34, 1.56, 0.64, 1);
        white-space: nowrap;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        position: relative;
        overflow: hidden;
      }
      .bc-suggestion::before {
        content: '→';
        margin-right: 6px;
        opacity: 0;
        transform: translateX(-4px);
        display: inline-block;
        transition: all 200ms ease;
        color: var(--bc-brand);
        font-weight: 700;
      }
      .bc-suggestion:hover {
        background: linear-gradient(135deg, color-mix(in srgb, var(--bc-brand) 8%, #fff), color-mix(in srgb, var(--bc-brand) 12%, #f8fafc));
        border-color: color-mix(in srgb, var(--bc-brand) 35%, transparent);
        color: var(--bc-brand);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px color-mix(in srgb, var(--bc-brand) 12%, transparent);
      }
      .bc-suggestion:hover::before {
        opacity: 1;
        transform: translateX(0);
      }

      /* ── Footer ── */
      .bc-footer { flex-shrink: 0; background: #fff; border-top: 1px solid var(--bc-line); }
      .bc-composer { display: flex; align-items: center; gap: 8px; padding: 12px; }
      .bc-input {
        min-width: 0; flex: 1; height: 42px; border: 1px solid #d0d5dd; border-radius: 8px;
        padding: 0 12px; color: var(--bc-text); background: #fff; outline: none; font-size: 14px;
        box-shadow: inset 0 1px 2px rgba(16,24,40,0.04);
      }
      .bc-input:focus { border-color: var(--bc-brand); box-shadow: 0 0 0 3px color-mix(in srgb, var(--bc-brand) 18%, transparent); }
      .bc-input::placeholder { color: #8a94a6; }
      .bc-send {
        width: 42px; height: 42px; border: 0; border-radius: 8px;
        color: #fff; background: var(--bc-brand);
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; flex: 0 0 auto;
      }
      .bc-send:hover { filter: brightness(0.96); }
      .bc-send:disabled { opacity: 0.58; cursor: default; }
      .bc-send svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
      .bc-powered { padding: 0 12px 9px; text-align: center; color: #98a2b3; font-size: 10px; line-height: 1.2; }
      .bc-powered a { color: #667085; font-weight: 700; text-decoration: none; }

      /* ── Mobile ── */
      @media (max-width: 480px) {
        .bc-panel { 
          width: calc(100vw - 20px) !important; 
          left: 10px !important; 
          right: 10px !important;
          top: 10vh !important;
          top: 10dvh !important;
          bottom: auto !important;
          height: calc(90vh - 84px) !important;
          height: calc(90dvh - 84px) !important;
          max-height: none !important;
          transform-origin: bottom center;
        }
        .bc-launcher { bottom: 18px; }
        .bc-shape-circle, .bc-shape-rounded, .bc-shape-square, .bc-shape-flower { width: 56px; height: 56px; }
        .bc-shape-pill { min-width: 56px; height: 52px; }
        .bc-launcher-text { display: none; }
        .bc-bubble { max-width: 82%; }
        .bc-teaser { max-width: 240px; bottom: 82px; font-size: 13px; }
      }
    `;
  }

  /* ── API ── */
  async function fetchConfig() {
    try {
      const res = await fetch(`${API_URL}/api/v1/public/widget-config`, { headers: reqHeaders() });
      if (!res.ok) return;
      const json = await res.json();
      if (json.success && json.data) Object.assign(cfg, json.data);
    } catch (e) { /* silent */ }
  }

  async function createSession() {
    try {
      const res = await fetch(`${API_URL}/api/v1/public/chat/session`, { method: "POST", headers: reqHeaders() });
      if (!res.ok) return;
      const json = await res.json();
      sessionId = json.data?.id || json.id || null;
    } catch (e) { /* silent */ }
  }

  async function sendQuery(question) {
    const h = reqHeaders();
    if (sessionId) h["X-Conversation-ID"] = sessionId;
    const res = await fetch(`${API_URL}/api/v1/public/chat/query`, {
      method: "POST", headers: h,
      body: JSON.stringify({ agent_id: AGENT_ID, question }),
    });
    if (!res.ok) {
      let msg = "Sorry, something went wrong. Please try again.";
      try {
        const errJson = await res.json();
        if (errJson.detail) msg = errJson.detail;
      } catch (e) { /* ignore parse error */ }
      throw new Error(msg);
    }
    const json = await res.json();
    return json.data?.answer || json.answer || "Sorry, I couldn't process that.";
  }

  /* ── Render: Messages ── */
  function renderMessage(msg) {
    const isUser = msg.from === "user";
    const row = el("div", { class: `bc-row ${isUser ? "bc-row-user bc-user" : "bc-bot"}` });
    if (!isUser) row.appendChild(el("div", { class: "bc-avatar" }, html(icon("bot"))));
    row.appendChild(el("div", { class: "bc-bubble" }, msg.text));
    return row;
  }

  function renderMessages(container) {
    messages.forEach(m => container.appendChild(renderMessage(m)));

    if (isLoading) {
      container.appendChild(
        el("div", { class: "bc-row bc-bot" },
          el("div", { class: "bc-avatar" }, html(icon("bot"))),
          el("div", { class: "bc-bubble" },
            el("div", { class: "bc-typing" }, el("span"), el("span"), el("span"))
          )
        )
      );
    }
  }

  /* ── Render: Launcher ── */
  function buildLauncher(side) {
    const shape = isOpen ? "circle" : (cfg.launcher_shape || "circle");
    const shapeClass = `bc-shape-${shape}`;
    const showText = !isOpen && (shape === "pill") && cfg.launcher_text;

    /* Entrance animation class — only on first render */
    let entranceClass = "";
    if (!hasEnteredView && !isOpen && cfg.entrance_animation && cfg.entrance_animation !== "none") {
      entranceClass = `bc-enter-${cfg.entrance_animation}`;
      hasEnteredView = true;
    }

    /* Extra classes */
    const extraClasses = [
      shapeClass,
      entranceClass,
      (!isOpen && cfg.glass_effect) ? "bc-glass" : "",
      (!isOpen && cfg.gradient_enabled) ? "bc-gradient" : "",
    ].filter(Boolean).join(" ");

    const btn = el("button", {
      class: `bc-launcher ${extraClasses}`,
      type: "button",
      "aria-label": isOpen ? "Close BolChat" : "Open BolChat",
      style: { [side]: "22px" },
      onClick: toggleChat,
    },
      html(icon(isOpen ? "close" : cfg.launcher_icon)),
      showText ? el("span", { class: "bc-launcher-text" }, cfg.launcher_text) : null,
      /* Attention dot */
      (!isOpen && cfg.attention_dot) ? el("span", { class: "bc-attention-dot" }) : null
    );

    /* Wrap with tooltip */
    if (!isOpen && cfg.tooltip_text) {
      const tooltipSide = side === "left" ? "bc-tooltip-left" : "bc-tooltip-right";
      const wrap = el("div", {
        class: "bc-tooltip-wrap",
        style: { position: "fixed", bottom: "22px", [side]: "22px", zIndex: "2147483646" },
      },
        el("div", { class: `bc-tooltip ${tooltipSide}` }, cfg.tooltip_text),
        btn
      );
      btn.style.position = "relative";
      btn.style.bottom = "auto";
      btn.style[side] = "auto";
      return wrap;
    }

    return btn;
  }

  /* ── Render: Teaser Bubble ── */
  function buildTeaser(side) {
    if (!cfg.teaser_text || isOpen || teaserDismissed) return null;
    const storageKey = `bc_teaser_${AGENT_ID}`;
    if (sessionStorage.getItem(storageKey)) return null;

    const teaserEl = el("div", {
      class: `bc-teaser ${side === "left" ? "bc-teaser-left" : ""}`,
      style: { [side]: "22px" },
      onClick: () => {
        sessionStorage.setItem(storageKey, "1");
        teaserDismissed = true;
        toggleChat();
      },
    },
      cfg.teaser_text,
      el("span", {
        class: "bc-teaser-close",
        onClick: (e) => {
          e.stopPropagation();
          sessionStorage.setItem(storageKey, "1");
          teaserDismissed = true;
          render();
        },
      }, "✕")
    );

    /* Auto dismiss after 8 seconds */
    if (teaserTimer) clearTimeout(teaserTimer);
    teaserTimer = setTimeout(() => {
      teaserDismissed = true;
      sessionStorage.setItem(storageKey, "1");
      render();
    }, 8000);

    return teaserEl;
  }

  /* ── Full Render ── */
  function render() {
    let root = document.getElementById("bolchat-widget-root");
    if (!root) {
      root = document.createElement("div");
      root.id = "bolchat-widget-root";
      document.body.appendChild(root);
      shadowRoot = root.attachShadow({ mode: "open" });
    }
    if (!shadowRoot) shadowRoot = root.shadowRoot || root.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = "";

    shadowRoot.appendChild(el("style", {}, buildCSS()));

    const side = isLeft() ? "left" : "right";

    /* Chat panel */
    const panel = el("section", {
      class: `bc-panel ${isOpen ? "bc-visible" : "bc-hidden"}`,
      "aria-live": "polite",
      style: { [side]: "22px" },
    });
    panel.appendChild(
      el("header", { class: "bc-header" },
        el("div", { class: "bc-header-mark" }, html(icon("bot"))),
        el("div", { class: "bc-title" },
          el("strong", {}, cfg.agent_name || "BolChat AI"),
          el("div", { class: "bc-status" }, el("span", { class: "bc-dot" }), "Online")
        ),
        el("button", { class: "bc-close", type: "button", "aria-label": "Close chat", onClick: toggleChat }, html(icon("close")))
      )
    );

    const msgContainer = el("div", { class: "bc-messages", id: "bc-messages" });
    renderMessages(msgContainer);
    panel.appendChild(msgContainer);

    const input = el("input", {
      class: "bc-input", id: "bc-input", type: "text",
      placeholder: "Type a message...", autocomplete: "off",
      onKeydown: e => { if (e.key === "Enter") handleSend(); },
    });
    const sendBtn = el("button", {
      class: "bc-send", id: "bc-send", type: "button",
      disabled: isLoading ? "true" : null,
      "aria-label": "Send message", onClick: handleSend,
    }, html(icon("send")));

    /* Suggested replies — above input, only before first user message */
    const replies = cfg.suggested_replies;
    const userSent = messages.some(m => m.from === "user");
    const suggestionsEl = (Array.isArray(replies) && replies.length > 0 && !userSent && !isLoading)
      ? el("div", { class: "bc-suggestions" },
        ...replies.slice(0, 3).map(text =>
          el("button", {
            class: "bc-suggestion", type: "button",
            onClick: () => { quickSend(text); },
          }, text)
        )
      )
      : null;

    const footer = el("footer", { class: "bc-footer" });
    if (suggestionsEl) footer.appendChild(suggestionsEl);
    footer.appendChild(el("div", { class: "bc-composer" }, input, sendBtn));
    footer.appendChild(el("div", { class: "bc-powered" }, "Powered by ", el("a", { href: "https://bolchat.ai", target: "_blank", rel: "noopener" }, "BolChat")));
    panel.appendChild(footer);

    shadowRoot.appendChild(panel);

    /* Teaser bubble (before launcher so it sits above) */
    const teaser = buildTeaser(side);
    if (teaser) shadowRoot.appendChild(teaser);

    /* Launcher */
    shadowRoot.appendChild(buildLauncher(side));

    requestAnimationFrame(() => {
      const mc = shadowRoot.getElementById("bc-messages");
      if (mc) mc.scrollTop = mc.scrollHeight;
      if (isOpen && !isLoading) {
        const inp = shadowRoot.getElementById("bc-input");
        if (inp) inp.focus();
      }
    });
  }

  /* ── Handlers ── */
  function toggleChat() {
    isOpen = !isOpen;
    if (isOpen) {
      teaserDismissed = true; /* close teaser when chat opens */
      if (messages.length === 0) {
        messages.push({ from: "bot", text: cfg.greeting || "Hi! How can I help you today?" });
        if (!sessionId) createSession();
      }
    }
    render();
  }

  function quickSend(text) {
    if (isLoading || !shadowRoot) return;
    messages.push({ from: "user", text });
    isLoading = true;
    render();
    sendQuery(text).then(answer => {
      messages.push({ from: "bot", text: answer });
    }).catch((err) => {
      messages.push({ from: "bot", text: err.message || "Sorry, something went wrong. Please try again." });
    }).finally(() => {
      isLoading = false;
      render();
    });
  }

  async function handleSend() {
    if (isLoading || !shadowRoot) return;
    const input = shadowRoot.getElementById("bc-input");
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    quickSend(text);
  }

  /* ── Boot ── */
  async function init() {
    await fetchConfig();
    hasEnteredView = false; /* reset so entrance animation plays */
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
