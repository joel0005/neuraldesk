# 🧠 NeuralDesk

**RAG-as-a-Service chatbot builder platform.** Build AI chatbots trained on your own data and deploy them anywhere with a single line of code.

---

## ✨ What is NeuralDesk?

NeuralDesk lets businesses create intelligent chatbots backed by their own knowledge — documents, websites, databases — without any machine learning expertise. Point it at your data, pick an LLM, embed the widget on your website. Done.

It's designed to be sold either as a **SaaS subscription** or as a **one-time on-premise installation** at client locations (fully packaged as a Windows `.exe` — no Docker, no cloud required).

---

## 🚀 Features

### Knowledge Sources
- 📄 **Files** — PDF, DOCX, CSV, Excel, JSON, TXT, Markdown, HTML
- 🌐 **URLs** — crawl any webpage and add its content
- 🗄️ **SQLite databases** — full Text-to-SQL engine; ask questions in plain English, get answers from your real data

### AI & Models
- 🤖 **Any LLM** — Ollama (local), OpenAI, Google Gemini, Anthropic Claude, Groq, Mistral
- 🔢 **Any embedding model** — local sentence-transformers or Ollama embedding models
- 🔄 **Dynamic model dropdowns** — live model lists fetched from each provider's API

### Deployment
- 🪄 **One-line embed code** — drop a `<script>` tag on any website
- 🎨 **Customizable widget** — color, position, persona name, welcome message
- 📱 **Multi-channel ready** — Telegram and WhatsApp integrations coming soon

### Security & Isolation
- 🔒 **Customer data isolation** — database answers are scoped to the logged-in customer automatically; one customer can never see another's rows
- 🧠 **Schema-first pipeline** — auto-detects table structure and customer-identifying columns at upload time; requires confirmation before any data goes live
- 🛡️ **Fail-safe SQL gatekeeper** — refuses to execute if a verified customer filter can't be confirmed in the generated SQL

### Dashboard
- 📊 **Analytics** — conversations, messages, satisfaction %, unanswered questions
- 🧪 **Test Chat** — test your bot with different customer IDs directly in the dashboard
- ⚙️ **Per-bot settings** — LLM, embedding model, persona, colors, suggested questions
- 🔑 **Plan-based bot limits** — free (1), pro (5), business (999), on-premise options

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10 + Flask |
| Database | SQLite (WAL mode) |
| Vector Store | Qdrant (target) / in-memory (dev) |
| Embeddings | sentence-transformers, Ollama |
| LLM routing | Custom router (Ollama, OpenAI, Gemini, Anthropic, Groq, Mistral) |
| Frontend | Vanilla JS dashboard + embeddable widget |
| Packaging | PyInstaller `--onedir` Windows `.exe` |

---

## 📁 Project Structure

```
ragbase/
├── app.py                  # Entry point, auto port detection, LAN IP banner
├── config.py               # Frozen-path-aware config (works in .exe too)
├── src/
│   ├── routes/
│   │   ├── auth.py         # JWT login/register
│   │   ├── bots.py         # Bot CRUD, plan enforcement
│   │   ├── chat.py         # /api/v1/chat — main chat endpoint
│   │   ├── knowledge.py    # File/URL/database upload + schema confirmation
│   │   └── analytics.py    # Conversation stats, unanswered questions
│   ├── rag/
│   │   └── pipeline.py     # RAG pipeline + Text-to-SQL gatekeeper
│   ├── sql/
│   │   └── engine.py       # Schema extraction, customer-column detection, SQL gen
│   ├── llm/
│   │   ├── router.py       # Routes to correct LLM provider
│   │   └── providers/      # ollama, openai, gemini, anthropic, groq, mistral
│   ├── embeddings/
│   │   └── service.py      # Local + Ollama embedding models
│   ├── vectordb/
│   │   └── store.py        # Vector upsert/search, dimension mismatch handling
│   ├── ingestion/
│   │   ├── service.py      # Orchestrates file/URL ingestion
│   │   ├── parsers.py      # PDF, DOCX, CSV, Excel, HTML parsers
│   │   └── chunker.py      # Smart text chunking
│   └── models/
│       └── database.py     # SQLite schema + safe migrations
├── static/
│   └── widget.js           # Embeddable chat widget
├── templates/
│   ├── dashboard.html
│   ├── bot.html            # Bot manager (Knowledge/Test/Settings/Deploy/Analytics)
│   └── ...
├── confirm_existing_bot.py # Helper: confirm already-uploaded databases
└── neuraldesk_test.db      # Sample database for testing customer isolation
```

---

## ⚡ Quick Start

### Requirements
- Python 3.10+
- [Ollama](https://ollama.ai) (optional, for local LLMs)

### Install

```bash
git clone https://github.com/joel0005/neuraldesk.git
cd neuraldesk
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

### First bot
1. Register an account
2. Create a bot
3. Upload a file, URL, or SQLite database in the Knowledge tab
4. Go to Deploy → copy the embed code → paste it on your website

---

## 🔒 Customer Data Isolation

When a bot is backed by a database (e.g. orders, support tickets), NeuralDesk automatically ensures each customer only ever sees their own rows — even if they ask a broad question like "show me all orders."

**How it works:**

1. **At upload time** — the schema is scanned for customer-identifying columns. Real foreign key relationships are detected first; naming patterns (`customer_id`, `user_id`, `client_id`, `account_id`) are used as fallback. The mapping is saved permanently and never re-runs.
2. **At confirmation** — you review the detected mapping in the dashboard and correct anything wrong before the source goes live. No data is retrieved until this step is complete.
3. **At query time** — the pipeline checks which tables the generated SQL touches. If any are customer-scoped, it verifies the SQL actually contains a `WHERE customer_id = '...'` filter before executing. No filter = refused, not guessed.

**To enable on your website:**
```html
<script src="https://your-neuraldesk-url/widget.js"
        data-bot-id="YOUR_BOT_ID"
        data-customer-id="LOGGED_IN_CUSTOMER_ID">
</script>
```

The `data-customer-id` should be set server-side by your own website, where the customer is already authenticated. NeuralDesk trusts whatever value the host page provides — authentication is your responsibility; isolation enforcement is NeuralDesk's.

---

## 📦 On-Premise Packaging

NeuralDesk can be packaged as a self-contained Windows executable for client delivery — no Python, no internet, no cloud required.

```bash
# Build the exe
pyinstaller app.spec

# Package for client
package_for_client.bat
```

Clients get a folder they can double-click to run. All paths (templates, static files, database, uploads, `.env`) resolve correctly whether running as source or as a frozen `.exe`.

> **Note:** Always use CPU-only PyTorch for packaging (`pip install torch --index-url https://download.pytorch.org/whl/cpu`) — GPU torch causes CUDA DLL errors in PyInstaller builds on non-GPU machines.

---

## 🗺️ Roadmap

- [ ] Telegram integration
- [ ] WhatsApp integration
- [ ] Stripe billing
- [ ] Docker packaging
- [ ] MySQL / PostgreSQL Text-to-SQL support
- [ ] Schema confirmation UI in dashboard
- [ ] Signed customer ID tokens (tamper-proof)
- [ ] Migration to Next.js + FastAPI + Qdrant + PostgreSQL + Redis

---

## 📄 License

Private — all rights reserved. Contact the author for licensing inquiries.

---

## 👤 Author

Built by [joel0005](https://github.com/joel0005)
