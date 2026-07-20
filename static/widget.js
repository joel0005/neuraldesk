(function() {
    const script = document.currentScript;
    const botId = script.getAttribute("data-bot-id");
    const apiUrl = script.getAttribute("data-api-url") || "http://localhost:5000";

    if (!botId) { console.error("NeuralDesk: data-bot-id is required"); return; }

    // Inject CSS
    const style = document.createElement("style");
    style.textContent = `
        #nd-bubble { position:fixed; bottom:24px; right:24px; width:56px; height:56px; border-radius:50%; background:var(--nd-color, #6366f1); color:#fff; border:none; cursor:pointer; box-shadow:0 4px 12px rgba(99,102,241,0.4); display:flex; align-items:center; justify-content:center; font-size:24px; z-index:99999; transition:transform 0.2s; }
        #nd-bubble:hover { transform:scale(1.1); }
        #nd-window { position:fixed; bottom:90px; right:24px; width:370px; height:520px; background:#fff; border-radius:16px; box-shadow:0 8px 30px rgba(0,0,0,0.12); display:none; flex-direction:column; z-index:99999; overflow:hidden; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
        #nd-window.nd-open { display:flex; }
        .nd-header { background:var(--nd-color, #6366f1); color:#fff; padding:16px; display:flex; align-items:center; gap:12px; }
        .nd-avatar { width:36px; height:36px; border-radius:50%; background:rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; font-size:18px; }
        .nd-hinfo { flex:1; }
        .nd-hname { font-size:15px; font-weight:600; }
        .nd-hstatus { font-size:12px; opacity:0.8; }
        .nd-close { background:none; border:none; color:#fff; font-size:20px; cursor:pointer; opacity:0.7; }
        .nd-close:hover { opacity:1; }
        .nd-msgs { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
        .nd-msg { max-width:82%; padding:10px 14px; border-radius:14px; font-size:14px; line-height:1.5; word-wrap:break-word; }
        .nd-bot { background:#f0f0f5; color:#1a1a2e; align-self:flex-start; border-bottom-left-radius:4px; }
        .nd-user { background:var(--nd-color, #6366f1);color:#fff; align-self:flex-end; border-bottom-right-radius:4px; }
        .nd-src { font-size:11px; color:#888; margin-top:8px; }
        .nd-msg strong { font-weight:600; }
        .nd-msg br + br { display:block; margin-top:6px; content:''; }
        .nd-typing { color:#888; font-style:italic; font-size:13px; }
        .nd-sq { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
        .nd-sq button { background:#fff; border:1px solid #ddd; border-radius:20px; padding:5px 12px; font-size:12px; cursor:pointer; color:#555; font-family:inherit; }
        .nd-sq button:hover { border-color:#6366f1; color:#6366f1; }
        .nd-input { display:flex; align-items:center; gap:8px; padding:12px 16px; border-top:1px solid #eee; }
        .nd-input input { flex:1; border:none; outline:none; font-size:14px; padding:8px; background:#f5f5f5; border-radius:8px; font-family:inherit; }
        .nd-input button { background:var(--nd-color, #6366f1); color:#fff; border:none; width:36px; height:36px; border-radius:50%; cursor:pointer; display:flex; align-items:center; justify-content:center; font-size:16px; }
        .nd-input button:disabled { opacity:0.5; }
        .nd-powered { text-align:center; padding:6px; font-size:10px; color:#bbb; }
        .nd-powered a { color:#999; text-decoration:none; }
    `;
    document.head.appendChild(style);

    // Inject HTML
    const html = `
        <button id="nd-bubble" onclick="NDChat.toggle()">💬</button>
        <div id="nd-window">
            <div class="nd-header">
                <div class="nd-avatar">🤖</div>
                <div class="nd-hinfo">
                    <div class="nd-hname" id="nd-name">Assistant</div>
                    <div class="nd-hstatus">Online</div>
                </div>
                <button class="nd-close" onclick="NDChat.toggle()">✕</button>
            </div>
            <div class="nd-msgs" id="nd-msgs"></div>
            <div class="nd-powered">Powered by <a href="#">NeuralDesk</a></div>
            <div class="nd-input">
                <input type="text" id="nd-input" placeholder="Type a message..." onkeydown="if(event.key==='Enter')NDChat.send()">
                <button onclick="NDChat.send()" id="nd-send">➤</button>
            </div>
        </div>
    `;
    const div = document.createElement("div");
    div.innerHTML = html;
    document.body.appendChild(div);

    // Chat logic
    window.NDChat = {
        convId: null,
        isOpen: false,
        config: null,

        async init() {
            try {
                const r = await fetch(`${apiUrl}/api/v1/bot-config/${botId}`);
                this.config = await r.json();
                // Apply bot color
                const color = this.config.primary_color || "#6366f1";
                document.getElementById("nd-bubble").style.background = color;
                document.documentElement.style.setProperty("--nd-color", color);
            } catch(e) {
                this.config = { bot_name: "Assistant", welcome_message: "Hi! How can I help?", suggested_questions: [] };
            }
        },

        toggle() {
            this.isOpen = !this.isOpen;
            document.getElementById("nd-window").classList.toggle("nd-open", this.isOpen);
            document.getElementById("nd-bubble").style.display = this.isOpen ? "none" : "flex";
            if (this.isOpen && document.getElementById("nd-msgs").children.length === 0) {
                this.welcome();
            }
        },

        welcome() {
            if (!this.config) { this.init().then(() => this.welcome()); return; }
            document.getElementById("nd-name").textContent = this.config.bot_name || "Assistant";

            // Show lead capture form first
            const container = document.getElementById("nd-msgs");
            const form = document.createElement("div");
            form.style.cssText = "background:#f8f8fc;border-radius:12px;padding:16px;margin-bottom:8px;";
            form.innerHTML = `
                <p style="font-size:14px;font-weight:600;color:#1a1a2e;margin:0 0 12px;">👋 Before we start, tell us about you</p>
                <input type="text" id="nd-visitor-name" placeholder="Your name" style="width:100%;padding:10px 12px;border:1px solid #e3e3ea;border-radius:8px;font-size:13px;margin-bottom:8px;outline:none;font-family:inherit;">
                <input type="email" id="nd-visitor-email" placeholder="Your email" style="width:100%;padding:10px 12px;border:1px solid #e3e3ea;border-radius:8px;font-size:13px;margin-bottom:10px;outline:none;font-family:inherit;">
                <button onclick="NDChat.startChat()" style="width:100%;padding:10px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">Start Chat</button>
                <p style="font-size:11px;color:#999;text-align:center;margin:8px 0 0;cursor:pointer;" onclick="NDChat.startChat()">or skip and chat now →</p>
            `;
            container.appendChild(form);
        },

        startChat() {
            const name = document.getElementById("nd-visitor-name")?.value?.trim() || "";
            const email = document.getElementById("nd-visitor-email")?.value?.trim() || "";
            this.visitorName = name;
            this.visitorEmail = email;

            // Save lead if email provided
            if (email) {
                fetch(`${apiUrl}/api/v1/lead`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bot_id: botId, name, email }),
                }).catch(() => {});
            }

            // Clear form and show welcome message
            const container = document.getElementById("nd-msgs");
            container.innerHTML = "";

            const greeting = name ? `Hi ${name}! ` : "";
            this.addMsg(greeting + (this.config.welcome_message || "How can I help you?"), "bot");

            const qs = this.config.suggested_questions || [];
            if (qs.length > 0) {
                const div = document.createElement("div");
                div.className = "nd-sq";
                qs.forEach(q => {
                    const btn = document.createElement("button");
                    btn.textContent = q;
                    btn.onclick = () => { document.getElementById("nd-input").value = q; this.send(); div.remove(); };
                    div.appendChild(btn);
                });
                container.appendChild(div);
                container.scrollTop = container.scrollHeight;
            }
        },
        addMsg(text, role, sources) {
            const container = document.getElementById("nd-msgs");
            const div = document.createElement("div");
            div.className = `nd-msg nd-${role}`;

            // Format text with bullet points and clean paragraphs
            const formatted = text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/^\* /gm, '• ')
                .replace(/^- /gm, '• ')
                .replace(/\n\n/g, '<br><br>')
                .replace(/\n/g, '<br>');
            div.innerHTML = formatted;

            // Show only source count, not filenames
            if (sources && sources.length > 0 && role === "bot") {
                const src = document.createElement("div");
                src.className = "nd-src";
                const avgScore = (sources.reduce((a, s) => a + s.score, 0) / sources.length).toFixed(1);
                src.innerHTML = `<span style="background:#eef2ff;color:#6366f1;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:500;">✓ Verified from ${sources.length} source${sources.length > 1 ? 's' : ''}</span>`;
                div.appendChild(src);
            }

            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return div;
        },

        async send() {
            const input = document.getElementById("nd-input");
            const msg = input.value.trim();
            if (!msg) return;
            input.value = "";
            this.addMsg(msg, "user");

            const typing = this.addMsg("Thinking...", "bot");
            typing.classList.add("nd-typing");
            document.getElementById("nd-send").disabled = true;

            try {
                const r = await fetch(`${apiUrl}/api/v1/chat`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bot_id: botId, message: msg, conversation_id: this.convId, visitor_name: this.visitorName || "", visitor_email: this.visitorEmail || "" }),
                });
                const data = await r.json();
                typing.remove();
                this.convId = data.conversation_id;
                this.addMsg(data.answer, "bot", data.sources || []);
            } catch(e) {
                typing.remove();
                this.addMsg("Sorry, something went wrong.", "bot");
            }
            document.getElementById("nd-send").disabled = false;
            input.focus();
        }
    };

    NDChat.init();
})();