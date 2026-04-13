/* BolChat Widget v2.0 */
(()=>{(function(){"use strict";let g=document.currentScript;if(!g)return;let y=g.getAttribute("data-key"),m=g.getAttribute("data-agent"),w=g.getAttribute("data-api-url")||"https://api.bolchat.ai";if(!y||!m){console.error("[BolChat] Missing data-key or data-agent on script tag.");return}let d=!1,u=null,p=!1,i=null,b=[],c={agent_name:"BolChat AI",brand_color:"#ec4899",greeting:"Hi! How can I help you today?",position:"bottom-right",launcher_icon:"chat",chat_height:560},k={chat:'<svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>',bot:'<svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="11" rx="4"/><path d="M12 5V3"/><path d="M8.5 13h.01"/><path d="M15.5 13h.01"/></svg>',headphones:'<svg viewBox="0 0 24 24"><path d="M4 15v-3a8 8 0 0 1 16 0v3"/><path d="M6 14h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H6z"/><path d="M18 14h-1a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h1z"/></svg>',help:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 0 1 5.1 1.3c0 1.8-2.6 2.2-2.6 3.7"/><path d="M12 17h.01"/></svg>',zap:'<svg viewBox="0 0 24 24"><path d="m13 2-9 12h8l-1 8 9-12h-8z"/></svg>',send:'<svg viewBox="0 0 24 24"><path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/></svg>',close:'<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'};function I(){return c.brand_color||"#ec4899"}function l(e){return k[e]||k.chat}function h(e){return{__html:e}}function t(e,o,...a){let r=document.createElement(e);return o&&Object.entries(o).forEach(([n,s])=>{s!=null&&(n==="style"&&typeof s=="object"?Object.assign(r.style,s):n.startsWith("on")&&typeof s=="function"?r.addEventListener(n.slice(2).toLowerCase(),s):r.setAttribute(n,String(s)))}),a.flat().forEach(n=>{n!=null&&(typeof n=="string"?r.appendChild(document.createTextNode(n)):n.__html!==void 0?r.insertAdjacentHTML("beforeend",n.__html):r.appendChild(n))}),r}function M(){let e=Number(c.chat_height)||560;return`
      :host {
        --bc-brand: ${I()};
        --bc-text: #172033;
        --bc-muted: #667085;
        --bc-line: #e5e7eb;
        --bc-surface: #ffffff;
        --bc-soft: #f6f7fb;
        all: initial;
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      * {
        box-sizing: border-box;
        letter-spacing: 0;
      }

      button,
      input {
        font: inherit;
      }

      .bc-launcher {
        position: fixed;
        bottom: 22px;
        z-index: 2147483646;
        width: 60px;
        height: 60px;
        border: 0;
        border-radius: 999px;
        color: #fff;
        background: var(--bc-brand);
        display: grid;
        place-items: center;
        cursor: pointer;
        box-shadow: 0 18px 44px rgba(16, 24, 40, 0.26);
        transition: transform 160ms ease, box-shadow 160ms ease;
      }

      .bc-launcher:hover {
        transform: translateY(-2px) scale(1.03);
        box-shadow: 0 22px 52px rgba(16, 24, 40, 0.3);
      }

      .bc-launcher svg,
      .bc-icon svg {
        width: 24px;
        height: 24px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .bc-panel {
        position: fixed;
        bottom: 94px;
        z-index: 2147483647;
        width: 390px;
        max-width: calc(100vw - 28px);
        height: ${e}px;
        max-height: calc(100vh - 118px);
        background: var(--bc-surface);
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 18px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        box-shadow: 0 26px 70px rgba(16, 24, 40, 0.24);
        transform-origin: bottom right;
        transition: opacity 180ms ease, transform 180ms ease;
      }

      .bc-panel.bc-hidden {
        opacity: 0;
        pointer-events: none;
        transform: translateY(14px) scale(0.97);
      }

      .bc-panel.bc-visible {
        opacity: 1;
        transform: translateY(0) scale(1);
      }

      .bc-header {
        min-height: 66px;
        padding: 14px 14px;
        color: #fff;
        background: linear-gradient(135deg, var(--bc-brand), color-mix(in srgb, var(--bc-brand) 82%, #111827));
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
      }

      .bc-header-mark {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        display: grid;
        place-items: center;
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.18);
        flex: 0 0 auto;
      }

      .bc-header-mark svg {
        width: 19px;
        height: 19px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .bc-title {
        min-width: 0;
        flex: 1;
      }

      .bc-title strong {
        display: block;
        font-size: 15px;
        line-height: 1.2;
        font-weight: 750;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .bc-status {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 4px;
        font-size: 11px;
        line-height: 1;
        color: rgba(255, 255, 255, 0.82);
      }

      .bc-dot {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: #34d399;
        box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.18);
      }

      .bc-close {
        width: 34px;
        height: 34px;
        border: 0;
        border-radius: 8px;
        display: grid;
        place-items: center;
        color: #fff;
        background: rgba(255, 255, 255, 0.16);
        cursor: pointer;
        flex: 0 0 auto;
      }

      .bc-close:hover {
        background: rgba(255, 255, 255, 0.26);
      }

      .bc-close svg {
        width: 18px;
        height: 18px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
      }

      .bc-messages {
        min-height: 0;
        flex: 1;
        overflow-y: auto;
        padding: 18px 14px 16px;
        background:
          radial-gradient(circle at top left, color-mix(in srgb, var(--bc-brand) 10%, transparent), transparent 34%),
          var(--bc-soft);
        display: flex;
        flex-direction: column;
        gap: 12px;
        scrollbar-width: thin;
        scrollbar-color: #cbd5e1 transparent;
      }

      .bc-row {
        display: flex;
        align-items: flex-end;
        gap: 8px;
        width: 100%;
      }

      .bc-row-user {
        justify-content: flex-end;
      }

      .bc-avatar {
        width: 26px;
        height: 26px;
        border-radius: 999px;
        display: grid;
        place-items: center;
        color: #fff;
        background: var(--bc-brand);
        flex: 0 0 auto;
        box-shadow: 0 6px 14px color-mix(in srgb, var(--bc-brand) 26%, transparent);
      }

      .bc-avatar svg {
        width: 14px;
        height: 14px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .bc-bubble {
        max-width: min(78%, 286px);
        padding: 11px 13px;
        border-radius: 14px;
        font-size: 14px;
        line-height: 1.48;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        box-shadow: 0 1px 1px rgba(16, 24, 40, 0.03);
      }

      .bc-bot .bc-bubble {
        color: var(--bc-text);
        background: #fff;
        border: 1px solid var(--bc-line);
        border-bottom-left-radius: 6px;
      }

      .bc-user .bc-bubble {
        color: #fff;
        background: var(--bc-brand);
        border-bottom-right-radius: 6px;
      }

      .bc-typing {
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 4px 0;
      }

      .bc-typing span {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: #94a3b8;
        animation: bc-bounce 1.1s infinite;
      }

      .bc-typing span:nth-child(2) { animation-delay: 120ms; }
      .bc-typing span:nth-child(3) { animation-delay: 240ms; }

      @keyframes bc-bounce {
        0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
        40% { transform: translateY(-4px); opacity: 1; }
      }

      .bc-footer {
        flex-shrink: 0;
        background: #fff;
        border-top: 1px solid var(--bc-line);
      }

      .bc-composer {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px;
      }

      .bc-input {
        min-width: 0;
        flex: 1;
        height: 42px;
        border: 1px solid #d0d5dd;
        border-radius: 8px;
        padding: 0 12px;
        color: var(--bc-text);
        background: #fff;
        outline: none;
        font-size: 14px;
        box-shadow: inset 0 1px 2px rgba(16, 24, 40, 0.04);
      }

      .bc-input:focus {
        border-color: var(--bc-brand);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--bc-brand) 18%, transparent);
      }

      .bc-input::placeholder {
        color: #8a94a6;
      }

      .bc-send {
        width: 42px;
        height: 42px;
        border: 0;
        border-radius: 8px;
        color: #fff;
        background: var(--bc-brand);
        display: grid;
        place-items: center;
        cursor: pointer;
        flex: 0 0 auto;
      }

      .bc-send:hover {
        filter: brightness(0.96);
      }

      .bc-send:disabled {
        opacity: 0.58;
        cursor: default;
      }

      .bc-send svg {
        width: 18px;
        height: 18px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .bc-powered {
        padding: 0 12px 9px;
        text-align: center;
        color: #98a2b3;
        font-size: 10px;
        line-height: 1.2;
      }

      .bc-powered a {
        color: #667085;
        font-weight: 700;
        text-decoration: none;
      }

      @media (max-width: 480px) {
        .bc-panel {
          width: calc(100vw - 20px);
          max-height: calc(100vh - 104px);
          bottom: 84px;
        }

        .bc-launcher {
          width: 56px;
          height: 56px;
          bottom: 18px;
        }

        .bc-bubble {
          max-width: 82%;
        }
      }
    `}function S(){return c.position==="bottom_left"||c.position==="bottom-left"}function v(){return{"Content-Type":"application/json","X-API-Key":y,"X-Agent-ID":m}}async function j(){try{let e=await fetch(`${w}/api/v1/public/widget-config`,{headers:v()});if(!e.ok)return;let o=await e.json();o.success&&o.data&&Object.assign(c,o.data)}catch{}}async function z(){try{let e=await fetch(`${w}/api/v1/public/chat/session`,{method:"POST",headers:v()});if(!e.ok)return;let o=await e.json();u=o.data?.id||o.id||null}catch{}}async function A(e){let o=v();u&&(o["X-Conversation-ID"]=u);let a=await fetch(`${w}/api/v1/public/chat/query`,{method:"POST",headers:o,body:JSON.stringify({agent_id:m,question:e})});if(!a.ok)throw new Error("Failed to get response");let r=await a.json();return r.data?.answer||r.answer||"Sorry, I couldn't process that."}function H(e){let o=e.from==="user",a=t("div",{class:`bc-row ${o?"bc-row-user bc-user":"bc-bot"}`});return o||a.appendChild(t("div",{class:"bc-avatar"},h(l("bot")))),a.appendChild(t("div",{class:"bc-bubble"},e.text)),a}function O(e){if(b.forEach(o=>e.appendChild(H(o))),p){let o=t("div",{class:"bc-row bc-bot"},t("div",{class:"bc-avatar"},h(l("bot"))),t("div",{class:"bc-bubble"},t("div",{class:"bc-typing"},t("span"),t("span"),t("span"))));e.appendChild(o)}}function x(){let e=document.getElementById("bolchat-widget-root");e||(e=document.createElement("div"),e.id="bolchat-widget-root",document.body.appendChild(e),i=e.attachShadow({mode:"open"})),i||(i=e.shadowRoot||e.attachShadow({mode:"open"})),i.innerHTML="";let o=t("style",{},M());i.appendChild(o);let a=S()?"left":"right",r=t("button",{class:"bc-launcher",type:"button","aria-label":d?"Close BolChat":"Open BolChat",style:{[a]:"22px"},onClick:C},h(l(d?"close":c.launcher_icon))),n=t("section",{class:`bc-panel ${d?"bc-visible":"bc-hidden"}`,"aria-live":"polite",style:{[a]:"22px"}});n.appendChild(t("header",{class:"bc-header"},t("div",{class:"bc-header-mark"},h(l("bot"))),t("div",{class:"bc-title"},t("strong",{},c.agent_name||"BolChat AI"),t("div",{class:"bc-status"},t("span",{class:"bc-dot"}),"Online")),t("button",{class:"bc-close",type:"button","aria-label":"Close chat",onClick:C},h(l("close")))));let s=t("div",{class:"bc-messages",id:"bc-messages"});O(s),n.appendChild(s);let T=t("input",{class:"bc-input",id:"bc-input",type:"text",placeholder:"Type a message...",autocomplete:"off",onKeydown:f=>{f.key==="Enter"&&_()}}),P=t("button",{class:"bc-send",id:"bc-send",type:"button",disabled:p?"true":null,"aria-label":"Send message",onClick:_},h(l("send")));n.appendChild(t("footer",{class:"bc-footer"},t("div",{class:"bc-composer"},T,P),t("div",{class:"bc-powered"},"Powered by ",t("a",{href:"https://bolchat.ai",target:"_blank",rel:"noopener"},"BolChat")))),i.appendChild(n),i.appendChild(r),requestAnimationFrame(()=>{let f=i.getElementById("bc-messages");if(f&&(f.scrollTop=f.scrollHeight),d&&!p){let E=i.getElementById("bc-input");E&&E.focus()}})}function C(){d=!d,d&&b.length===0&&(b.push({from:"bot",text:c.greeting||"Hi! How can I help you today?"}),u||z()),x()}async function _(){if(p||!i)return;let e=i.getElementById("bc-input");if(!e)return;let o=e.value.trim();if(o){e.value="",b.push({from:"user",text:o}),p=!0,x();try{let a=await A(o);b.push({from:"bot",text:a})}catch{b.push({from:"bot",text:"Sorry, something went wrong. Please try again."})}finally{p=!1,x()}}}async function B(){await j(),x()}document.readyState==="loading"?document.addEventListener("DOMContentLoaded",B):B()})();})();
