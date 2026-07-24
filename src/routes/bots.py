"""Bot Routes — create, list, update, delete bots."""

import uuid
import re
from flask import Blueprint, request, jsonify
from ..models.database import get_db
from .auth import get_current_user

bots = Blueprint("bots", __name__)


def require_login():
    user = get_current_user()
    if not user:
        return None, jsonify({"error": "Login required"}), 401
    return user, None, None


@bots.route("/api/bots", methods=["POST"])
def create_bot():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    # Check bot limit based on plan
    db = get_db()
    current_count = db.execute("SELECT COUNT(*) as cnt FROM bots WHERE user_id = ?", (user["id"],)).fetchone()["cnt"]

    plan_limits = {
        "free": 1,
        "pro": 5,
        "business": 999,
        "enterprise": 999,
        "onpremise": 1,
        "onpremise_5": 5,
        "onpremise_unlimited": 999,
    }

    user_plan = user.get("plan") or "free"
    max_bots = plan_limits.get(user_plan, 1)

    if current_count >= max_bots:
        db.close()
        return jsonify({"error": f"Bot limit reached. Your plan ({user_plan}) allows {max_bots} bot(s). Contact admin to upgrade."}), 403

    data = request.json
    name = data.get("name", "My Bot")
    bot_id = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + "-" + bot_id[:6]

    
    db.execute(
        """INSERT INTO bots (id, user_id, name, slug, description, llm_provider, llm_model,
           system_prompt, persona_name, welcome_message, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bot_id, user["id"], name, slug,
            data.get("description", ""),
            data.get("llm_provider", "ollama"),
            data.get("llm_model", "gemma3:latest"),
            data.get("system_prompt", ""),
            data.get("persona_name", "Assistant"),
            data.get("welcome_message", "Hi! How can I help you?"),
            "active",
        ),
    )
    db.commit()
    db.close()

    return jsonify({"id": bot_id, "name": name, "slug": slug, "status": "active"})


@bots.route("/api/bots", methods=["GET"])
def list_bots():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    rows = db.execute("SELECT id, name, slug, status, llm_provider, llm_model, created_at FROM bots WHERE user_id = ?", (user["id"],)).fetchall()
    db.close()

    return jsonify([dict(r) for r in rows])


@bots.route("/api/bots/<bot_id>", methods=["GET"])
def get_bot(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    bot = db.execute("SELECT * FROM bots WHERE id = ? AND user_id = ?", (bot_id, user["id"])).fetchone()
    db.close()

    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    return jsonify(dict(bot))


@bots.route("/api/bots/<bot_id>", methods=["PUT"])
def update_bot(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.json
    allowed = [
        "name", "description", "status", "llm_provider", "llm_model", "llm_api_key", "temperature",
        "max_tokens", "system_prompt", "persona_name", "welcome_message", "fallback_message",
        "suggested_questions", "blocked_words", "top_k", "similarity_threshold",
        "confidence_threshold", "use_reranking", "use_query_rewrite", "require_citations",
        "primary_color", "position", "embedding_provider", "embedding_model",
    ]

    updates = []
    values = []
    for key in allowed:
        if key in data:
            updates.append(f"{key} = ?")
            values.append(data[key] if not isinstance(data[key], list) else str(data[key]))

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    values.extend([bot_id, user["id"]])
    db = get_db()
    db.execute(f"UPDATE bots SET {', '.join(updates)} WHERE id = ? AND user_id = ?", values)
    db.commit()
    db.close()

    return jsonify({"message": "Bot updated", "bot_id": bot_id})


@bots.route("/api/bots/<bot_id>", methods=["DELETE"])
def delete_bot(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    db.execute("DELETE FROM bots WHERE id = ? AND user_id = ?", (bot_id, user["id"]))
    db.commit()
    db.close()

    return jsonify({"message": "Bot deleted"})


@bots.route("/api/bots/<bot_id>/embed-code", methods=["GET"])
def embed_code(bot_id):
    code = f'<script src="https://cdn.ragbase.com/widget.js" data-bot-id="{bot_id}" async></script>'
    return jsonify({"embed_code": code, "bot_id": bot_id})