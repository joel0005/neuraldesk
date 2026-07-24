from flask import Flask, jsonify
from flask_cors import CORS
from src.config import config
from src.models.database import init_db
from src.routes.analytics import analytics
from flask import Flask, jsonify, render_template
from src.routes.admin import admin
import sys, os

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, "templates")
    static_folder = os.path.join(sys._MEIPASS, "static")
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)

app.config["SECRET_KEY"] = config.SECRET_KEY
CORS(app)
@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
init_db()

from src.routes.auth import auth
from src.routes.bots import bots
from src.routes.knowledge import knowledge
from src.routes.chat import chat

app.register_blueprint(auth)
app.register_blueprint(bots)
app.register_blueprint(knowledge)
app.register_blueprint(chat)
app.register_blueprint(analytics)
app.register_blueprint(admin)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "RagBase", "version": "0.1.0"})


@app.route("/api/providers")
def providers():
    from src.llm.router import llm_router
    return jsonify({"providers": llm_router.list_available()})


@app.route("/api/supported-files")
def supported_files():
    from src.ingestion.parsers import supported_types
    return jsonify({"file_types": supported_types()})
@app.route("/debug/<bot_id>")
def debug_bot(bot_id):
    from src.vectordb.store import VectorStore
    from src.embeddings.service import EmbeddingService

    vs = VectorStore()
    emb = EmbeddingService()
    collection = f"bot_{bot_id}"

    # Check what's on disk
    import os
    store_path = os.path.join(os.path.dirname(__file__), "db_data", "vectors", collection)
    files_exist = os.path.exists(store_path)
    files_list = os.listdir(store_path) if files_exist else []

    # Try to load and search
    count = vs.count(collection)
    query_vec = emb.embed_query("name of candidate")
    results = vs.search(collection, query_vec, top_k=3)

    return jsonify({
        "collection": collection,
        "store_path": store_path,
        "path_exists": files_exist,
        "files": files_list,
        "vector_count": count,
        "search_results": [{"score": r.score, "content": r.content[:200]} for r in results],
    })
@app.route("/debug/chat/<bot_id>/<message>")
def debug_chat(bot_id, message):
    from src.models.database import get_db
    from src.rag.pipeline import RAGPipeline

    db = get_db()
    bot = db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    db.close()

    if not bot:
        return jsonify({"error": "Bot not found"})

    bot = dict(bot)

    pipeline = RAGPipeline(bot)
    result = pipeline.run(query=message)

    return jsonify(result)

@app.route("/api/v1/bot-config/<bot_id>")
def bot_config(bot_id):
    """Public endpoint — widget calls this to get bot settings."""
    from src.models.database import get_db
    import json

    db = get_db()
    bot = db.execute("SELECT name, persona_name, welcome_message, suggested_questions, primary_color FROM bots WHERE id = ?", (bot_id,)).fetchone()
    db.close()

    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    bot = dict(bot)
    try:
        questions = json.loads(bot.get("suggested_questions") or "[]")
    except:
        questions = []

    return jsonify({
        "bot_name": bot.get("persona_name") or bot.get("name") or "Assistant",
        "welcome_message": bot.get("welcome_message") or "Hi! How can I help you?",
        "suggested_questions": questions,
        "primary_color": bot.get("primary_color") or "#6366f1",
    })

from flask import render_template

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/bot/<bot_id>")
def bot_page(bot_id):
    return render_template("bot.html")

@app.route("/")
def home():
    if config.DEPLOYMENT_MODE == "onpremise":
        return render_template("login.html")
    return render_template("landing.html")
@app.route("/widget.js")
def widget_js():
    return app.send_static_file("widget.js")
@app.route("/settings")
def settings_page():
    return render_template("settings.html")

@app.route("/docs")
def docs_page():
    return render_template("docs.html")
@app.route("/api/models/local")
def local_models():
    from src.llm.ollama_provider import OllamaProvider
    p = OllamaProvider()
    models = p.list_local_models()
    return jsonify({"models": models})
@app.route("/api/models/embeddings")
def embedding_models():
    from src.embeddings.service import EmbeddingService
    local_ids, local_labels = EmbeddingService.list_local_models()
    ollama_models = EmbeddingService.list_ollama_models()
    return jsonify({"local": local_ids, "local_labels": local_labels, "ollama": ollama_models})
@app.route("/admin")
def admin_page():
    return render_template("admin.html")

if __name__ == "__main__":
    import socket

    def find_free_port(preferred=5000):
        port = preferred
        while port < preferred + 100:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("0.0.0.0", port))
                s.close()
                return port
            except OSError:
                port += 1
        return preferred

    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    port = find_free_port(5000)
    local_ip = get_local_ip()

    print("\n==========================================")
    print("  NeuralDesk is running!")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Network: http://{local_ip}:{port}")
    print(f"  Admin:   http://localhost:{port}/admin")
    print("  Press Ctrl+C to stop")
    print("==========================================\n")

    app.run(host="0.0.0.0", debug=False, port=port, use_reloader=False)