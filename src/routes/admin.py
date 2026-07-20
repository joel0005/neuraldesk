"""Admin Routes — only you (the owner) can access these."""

from flask import Blueprint, request, jsonify
from ..models.database import get_db

admin = Blueprint("admin", __name__)

ADMIN_SECRET = "Joeladmin@123" # Change this to your secret key


def check_admin():
    key = request.headers.get("X-Admin-Key", "")
    return key == ADMIN_SECRET


@admin.route("/api/admin/users", methods=["GET"])
def list_users():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    users = db.execute("SELECT id, email, name, plan, created_at FROM users").fetchall()
    db.close()
    return jsonify([dict(u) for u in users])


@admin.route("/api/admin/users/<user_id>/plan", methods=["PUT"])
def set_plan(user_id):
    """Change a user's plan — controls how many bots they can create."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    plan = data.get("plan", "free")

    valid_plans = ["free", "pro", "business", "enterprise", "onpremise", "onpremise_5", "onpremise_unlimited"]
    if plan not in valid_plans:
        return jsonify({"error": f"Invalid plan. Use: {valid_plans}"}), 400

    db = get_db()
    db.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
    db.commit()
    db.close()

    plan_limits = {
        "free": 1, "pro": 5, "business": 999, "enterprise": 999,
        "onpremise": 1, "onpremise_5": 5, "onpremise_unlimited": 999,
    }

    return jsonify({
        "message": f"Plan updated to {plan}",
        "bot_limit": plan_limits.get(plan, 1),
    })


@admin.route("/api/admin/users/<user_id>/bots", methods=["GET"])
def user_bots(user_id):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    bots = db.execute("""
        SELECT b.id, b.name, b.status, b.llm_provider, b.llm_model, b.created_at,
        (SELECT COUNT(*) FROM knowledge_sources WHERE bot_id = b.id) as source_count,
        (SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE c.bot_id = b.id) as message_count,
        (SELECT MAX(m.created_at) FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE c.bot_id = b.id) as last_message_at
        FROM bots b WHERE b.user_id = ?
    """, (user_id,)).fetchall()
    db.close()
    return jsonify([dict(b) for b in bots])


@admin.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    """Overall platform stats."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    users = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    bots = db.execute("SELECT COUNT(*) as cnt FROM bots").fetchone()["cnt"]
    messages = db.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
    sources = db.execute("SELECT COUNT(*) as cnt FROM knowledge_sources").fetchone()["cnt"]
    db.close()
    return jsonify({
        "total_users": users,
        "total_bots": bots,
        "total_messages": messages,
        "total_sources": sources,
    })
@admin.route("/api/admin/bots/<bot_id>", methods=["DELETE"])
def admin_delete_bot(bot_id):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    db.execute("DELETE FROM knowledge_sources WHERE bot_id = ?", (bot_id,))
    db.execute("DELETE FROM conversations WHERE bot_id = ?", (bot_id,))
    db.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
    db.commit()
    db.close()
    return jsonify({"message": "Bot deleted"})


@admin.route("/api/admin/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):



    """Delete a user and all their data."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    db = get_db()
    db.execute("DELETE FROM bots WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    db.close()
    return jsonify({"message": "User deleted"})