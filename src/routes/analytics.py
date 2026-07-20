"""Analytics Routes — stats, unanswered questions, leads, conversations."""

from flask import Blueprint, request, jsonify
from ..models.database import get_db
from .auth import get_current_user

analytics = Blueprint("analytics", __name__)


@analytics.route("/api/bots/<bot_id>/analytics", methods=["GET"])
def overview(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()

    # Total conversations
    conv_count = db.execute(
        "SELECT COUNT(*) as cnt FROM conversations WHERE bot_id = ?", (bot_id,)
    ).fetchone()["cnt"]

    # Total messages
    msg_count = db.execute(
        """SELECT COUNT(*) as cnt FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.bot_id = ?""", (bot_id,)
    ).fetchone()["cnt"]

    # Average confidence
    avg_conf = db.execute(
        """SELECT AVG(confidence) as avg FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.bot_id = ? AND m.role = 'assistant' AND m.confidence IS NOT NULL""", (bot_id,)
    ).fetchone()["avg"] or 0

    # Feedback
    thumbs_up = db.execute(
        """SELECT COUNT(*) as cnt FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.bot_id = ? AND m.feedback = 'thumbs_up'""", (bot_id,)
    ).fetchone()["cnt"]

    thumbs_down = db.execute(
        """SELECT COUNT(*) as cnt FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.bot_id = ? AND m.feedback = 'thumbs_down'""", (bot_id,)
    ).fetchone()["cnt"]

    # Unanswered
    unanswered = db.execute(
        "SELECT COUNT(*) as cnt FROM unanswered_questions WHERE bot_id = ? AND resolved = 0", (bot_id,)
    ).fetchone()["cnt"]

    # Leads
    leads_count = db.execute(
        "SELECT COUNT(*) as cnt FROM leads WHERE bot_id = ?", (bot_id,)
    ).fetchone()["cnt"]

    db.close()

    total_feedback = thumbs_up + thumbs_down
    satisfaction = round(thumbs_up / max(total_feedback, 1) * 100, 1)

    return jsonify({
        "total_conversations": conv_count,
        "total_messages": msg_count,
        "avg_confidence": round(avg_conf, 2),
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "satisfaction_pct": satisfaction,
        "unanswered_questions": unanswered,
        "leads_captured": leads_count,
    })


@analytics.route("/api/bots/<bot_id>/analytics/unanswered", methods=["GET"])
def unanswered(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    rows = db.execute(
        """SELECT id, question, frequency, first_asked_at, last_asked_at
           FROM unanswered_questions WHERE bot_id = ? AND resolved = 0
           ORDER BY frequency DESC LIMIT 50""", (bot_id,)
    ).fetchall()
    db.close()

    return jsonify([dict(r) for r in rows])


@analytics.route("/api/bots/<bot_id>/analytics/conversations", methods=["GET"])
def conversations(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    offset = (page - 1) * limit

    db = get_db()
    total = db.execute("SELECT COUNT(*) as cnt FROM conversations WHERE bot_id = ?", (bot_id,)).fetchone()["cnt"]
    rows = db.execute(
        """SELECT id, session_id, visitor_name, visitor_email, channel, status,
                  message_count, last_message_at, created_at
           FROM conversations WHERE bot_id = ?
           ORDER BY last_message_at DESC LIMIT ? OFFSET ?""", (bot_id, limit, offset)
    ).fetchall()
    db.close()

    return jsonify({"total": total, "page": page, "conversations": [dict(r) for r in rows]})


@analytics.route("/api/bots/<bot_id>/analytics/conversation/<conv_id>", methods=["GET"])
def conversation_detail(bot_id, conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    messages = db.execute(
        """SELECT id, role, content, sources_used, confidence, model_used,
                  feedback, latency_ms, created_at
           FROM messages WHERE conversation_id = ?
           ORDER BY created_at ASC""", (conv_id,)
    ).fetchall()
    db.close()

    return jsonify([dict(m) for m in messages])


@analytics.route("/api/bots/<bot_id>/analytics/leads", methods=["GET"])
def leads(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    rows = db.execute(
        "SELECT * FROM leads WHERE bot_id = ? ORDER BY created_at DESC LIMIT 100", (bot_id,)
    ).fetchall()
    db.close()

    return jsonify([dict(r) for r in rows])