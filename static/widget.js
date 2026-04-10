/* BolChat Widget v1.0 — https://bolchat.ai */
(()=>{(function(){"use strict";let b=document.currentScript;if(!b)return;let m=b.getAttribute("data-key"),f=b.getAttribute("data-agent"),u=b.getAttribute("data-api-url")||"https://api.bolchat.ai";if(!m||!f){console.error("[BolChat] Missing data-key or data-agent on script tag.");return}let d=!1,h=null,l=[],i={agent_name:"Assistant",brand_color:"#f43f5e",greeting:"Hi! How can I help you today?",position:"bottom-right",launcher_icon:"chat",chat_height:520},v={chat:'<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',bot:'<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7v3a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4v-3a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/></svg>',headphones:'<svg viewBox="0 0 24 24"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>',help:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',zap:'<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'},x='<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7v3a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4v-3a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/></svg>',j='<svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',w='<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';function E(){return v[i.launcher_icon]||v.chat}function S(){return`
    #bolchat-widget-root * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    #bolchat-launcher {
      position: fixed; bottom: 20px; z-index: 2147483646;
      width: 56px; height: 56px; border-radius: 50%; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.18); transition: transform 0.2s;
    }
    #bolchat-launcher:hover { transform: scale(1.1); }
    #bolchat-launcher svg { width: 26px; height: 26px; fill: none; stroke: #fff; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    #bolchat-panel {
      position: fixed; bottom: 88px; z-index: 2147483647;
      width: 370px; max-width: calc(100vw - 32px); height: ${i.chat_height||520}px; max-height: calc(100vh - 120px);
      border-radius: 16px; overflow: hidden; display: flex; flex-direction: column;
      box-shadow: 0 12px 48px rgba(0,0,0,0.22); background: #fff;
      transition: opacity 0.2s, transform 0.2s;
    }
    #bolchat-panel.bc-hidden { opacity: 0; transform: translateY(12px) scale(0.95); pointer-events: none; }
    #bolchat-panel.bc-visible { opacity: 1; transform: translateY(0) scale(1); }
    .bc-header { padding: 14px 16px; display: flex; align-items: center; gap: 10px; color: #fff; flex-shrink: 0; }
    .bc-header-avatar { width: 34px; height: 34px; border-radius: 50%; background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; }
    .bc-header-avatar svg { width: 18px; height: 18px; fill: none; stroke: #fff; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .bc-header-info { flex: 1; min-width: 0; }
    .bc-header-name { font-weight: 700; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .bc-header-status { font-size: 10px; opacity: 0.8; display: flex; align-items: center; gap: 4px; margin-top: 2px; }
    .bc-header-dot { width: 6px; height: 6px; border-radius: 50%; background: #4ade80; }
    .bc-header-close { background: rgba(255,255,255,0.2); border: none; border-radius: 8px; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: background 0.15s; }
    .bc-header-close:hover { background: rgba(255,255,255,0.35); }
    .bc-header-close svg { width: 16px; height: 16px; stroke: #fff; fill: none; stroke-width: 2; }
    .bc-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; background: #f8fafc; min-height: 0; }
    .bc-msg { display: flex; gap: 8px; max-width: 100%; }
    .bc-msg.bc-user { flex-direction: row-reverse; }
    .bc-msg-avatar { width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; margin-top: 2px; }
    .bc-msg-avatar svg { width: 14px; height: 14px; fill: none; stroke: #fff; stroke-width: 2; }
    .bc-msg-avatar.bc-user-av { background: #cbd5e1; }
    .bc-msg-avatar.bc-user-av svg { stroke: #475569; }
    .bc-bubble { padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.5; max-width: 75%; word-wrap: break-word; }
    .bc-bot .bc-bubble { background: #fff; color: #334155; border: 1px solid #e2e8f0; border-top-left-radius: 4px; }
    .bc-user .bc-bubble { color: #fff; border-top-right-radius: 4px; }
    .bc-typing { display: flex; gap: 4px; padding: 10px 14px; }
    .bc-typing span { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; animation: bc-bounce 1.2s infinite; }
    .bc-typing span:nth-child(2) { animation-delay: 0.15s; }
    .bc-typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes bc-bounce { 0%,80%,100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
    .bc-input-area { padding: 10px 12px; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; align-items: center; flex-shrink: 0; background: #fff; }
    .bc-input { flex: 1; height: 38px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0 12px; font-size: 13px; outline: none; background: #f8fafc; color: #1e293b; }
    .bc-input:focus { border-color: #94a3b8; }
    .bc-input::placeholder { color: #94a3b8; }
    .bc-send { width: 38px; height: 38px; border: none; border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: transform 0.15s; }
    .bc-send:hover { transform: scale(1.05); }
    .bc-send:disabled { opacity: 0.5; cursor: default; transform: none; }
    .bc-send svg { width: 16px; height: 16px; fill: none; stroke: #fff; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .bc-powered { padding: 5px 0; text-align: center; font-size: 9px; color: #94a3b8; border-top: 1px solid #f1f5f9; background: #fafbfc; flex-shrink: 0; }
    .bc-powered a { color: #64748b; text-decoration: none; font-weight: 700; }
    .bc-powered a:hover { text-decoration: underline; }
    `}function t(e,n,...s){let o=document.createElement(e);return n&&Object.entries(n).forEach(([a,p])=>{a==="style"&&typeof p=="object"?Object.assign(o.style,p):a.startsWith("on")?o.addEventListener(a.slice(2).toLowerCase(),p):o.setAttribute(a,p)}),s.flat().forEach(a=>{typeof a=="string"?o.innerHTML+=a:a&&o.appendChild(a)}),o}let y=()=>({"Content-Type":"application/json","X-API-Key":m,"X-Agent-ID":f});async function z(){try{let e=await fetch(`${u}/api/v1/public/widget-config`,{headers:y()});if(e.ok){let n=await e.json();n.success&&n.data&&Object.assign(i,n.data)}}catch{}}async function O(){try{let e=await fetch(`${u}/api/v1/public/chat/session`,{method:"POST",headers:y()});if(e.ok){let n=await e.json();h=n.data?.id||n.id}}catch{}}async function H(e){let n={...y()};h&&(n["X-Conversation-ID"]=h);let s=await fetch(`${u}/api/v1/public/chat/query`,{method:"POST",headers:n,body:JSON.stringify({agent_id:f,question:e})});if(!s.ok)throw new Error("Failed to get response");let o=await s.json();return o.data?.answer||o.answer||"Sorry, I couldn't process that."}function g(){let e=document.getElementById("bolchat-widget-root");e&&e.remove();let n=t("div",{id:"bolchat-widget-root"});n.appendChild(t("style",{},S()));let s=i.position!=="bottom_left"&&i.position!=="bottom-left",o=t("button",{id:"bolchat-launcher",style:{background:i.brand_color,[s?"right":"left"]:"20px"},onClick:k},d?w:E());n.appendChild(o);let a=t("div",{id:"bolchat-panel",class:d?"bc-visible":"bc-hidden",style:{[s?"right":"left"]:"20px"}}),p=t("div",{class:"bc-header",style:{background:i.brand_color}},t("div",{class:"bc-header-avatar"},x),t("div",{class:"bc-header-info"},t("div",{class:"bc-header-name"},i.agent_name),t("div",{class:"bc-header-status"},t("span",{class:"bc-header-dot"}),"Online")),t("button",{class:"bc-header-close",onClick:k},w));a.appendChild(p);let B=t("div",{class:"bc-messages",id:"bc-messages"});l.forEach(r=>{let c=r.from==="user",L=c?"bc-msg-avatar bc-user-av":"bc-msg-avatar",N=c?{}:{background:i.brand_color},P=c?{background:i.brand_color}:{},D=t("div",{class:`bc-msg ${c?"bc-user":"bc-bot"}`},t("div",{class:L,style:N},c?'<svg viewBox="0 0 24 24" style="width:14px;height:14px;fill:none;stroke:#475569;stroke-width:2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>':x),t("div",{class:"bc-bubble",style:P},r.text));B.appendChild(D)}),a.appendChild(B);let A=t("input",{class:"bc-input",type:"text",placeholder:"Type a message...",id:"bc-input",onKeydown:r=>{r.key==="Enter"&&_()}}),T=t("button",{class:"bc-send",id:"bc-send-btn",style:{background:i.brand_color},onClick:_},j);a.appendChild(t("div",{class:"bc-input-area"},A,T)),a.appendChild(t("div",{class:"bc-powered"},'Powered by <a href="https://bolchat.ai" target="_blank" rel="noopener">BolChat</a>')),n.appendChild(a),document.body.appendChild(n),requestAnimationFrame(()=>{let r=document.getElementById("bc-messages");if(r&&(r.scrollTop=r.scrollHeight),d){let c=document.getElementById("bc-input");c&&c.focus()}})}function k(){d=!d,d&&l.length===0&&(l.push({from:"bot",text:i.greeting}),h||O()),g()}function M(){let e=document.getElementById("bc-messages");if(!e)return;let n=t("div",{class:"bc-msg bc-bot",id:"bc-typing"},t("div",{class:"bc-msg-avatar",style:{background:i.brand_color}},x),t("div",{class:"bc-bubble"},t("div",{class:"bc-typing"},t("span"),t("span"),t("span"))));e.appendChild(n),e.scrollTop=e.scrollHeight}function C(){let e=document.getElementById("bc-typing");e&&e.remove()}async function _(){let e=document.getElementById("bc-input"),n=document.getElementById("bc-send-btn");if(!e)return;let s=e.value.trim();if(s){e.value="",l.push({from:"user",text:s}),g(),M(),n&&(n.disabled=!0);try{let o=await H(s);C(),l.push({from:"bot",text:o})}catch{C(),l.push({from:"bot",text:"Sorry, something went wrong. Please try again."})}g()}}async function I(){await z(),g()}document.readyState==="loading"?document.addEventListener("DOMContentLoaded",I):I()})();})();
