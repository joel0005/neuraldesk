"""Chat Route — the main endpoint where users talk to the bot."""

import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from ..models.database import get_db
from ..rag.pipeline import RAGPipeline

chat = Blueprint("chat", __name__)


@chat.route("/api/v1/chat", methods=["POST"])
def send_message():
    data = request.json
    bot_id = data.get("bot_id", "")
    message = data.get("message", "").strip()
    session_id = data.get("session_id", str(uuid.uuid4()))
    conversation_id = data.get("conversation_id")
    customer_id = data.get("customer_id")

    if not bot_id or not message:
        return jsonify({"error": "bot_id and message required"}), 400

    db = get_db()

    # Get bot
    bot = db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    if not bot:
        db.close()
        return jsonify({"error": "Bot not found"}), 404

    bot = dict(bot)
    if bot["status"] != "active":
        db.close()
        return jsonify({"error": "Bot is not active"}), 403

    # Get or create conversation
    if conversation_id:
        conv = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    else:
        conv = db.execute(
            "SELECT * FROM conversations WHERE bot_id = ? AND session_id = ? AND status = 'active'",
            (bot_id, session_id),
        ).fetchone()

    if not conv:
        conversation_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO conversations (id, bot_id, session_id, visitor_name, visitor_email, first_message_at) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, bot_id, session_id, data.get("visitor_name"), data.get("visitor_email"), datetime.utcnow()),
        )
        db.commit()
    else:
        conversation_id = conv["id"]

    # Save user message
    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
        (user_msg_id, conversation_id, "user", message),
    )

    # Get conversation history
    history_rows = db.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 10",
        (conversation_id,),
    ).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

    # Run RAG pipeline
    try:
        pipeline = RAGPipeline(bot)
        # customer_id is only used by the Text-to-SQL path (_try_sql) to scope
        # database queries to this customer's own rows. Document/URL RAG is
        # untouched and ignores it entirely.
        rag_result = pipeline.run(query=message, conversation_history=history, customer_id=customer_id)
    except Exception as e:
        print(f"\n!!! RAG ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        rag_result = {
            "answer": bot.get("fallback_message", "Sorry, something went wrong."),
            "sources": [], "confidence": 0.0, "model_used": "", "provider_used": "",
            "tokens_input": 0, "tokens_output": 0, "latency_ms": 0, "is_fallback": True,
        }

    # Save assistant message
    assistant_msg_id = str(uuid.uuid4())
    import json
    db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, sources_used, confidence,
           model_used, provider_used, tokens_input, tokens_output, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            assistant_msg_id, conversation_id, "assistant", rag_result["answer"],
            json.dumps(rag_result["sources"]), rag_result["confidence"],
            rag_result["model_used"], rag_result["provider_used"],
            rag_result["tokens_input"], rag_result["tokens_output"], rag_result["latency_ms"],
        ),
    )

    # Update conversation
    db.execute(
        "UPDATE conversations SET message_count = message_count + 2, last_message_at = ? WHERE id = ?",
        (datetime.utcnow(), conversation_id),
    )

    # Track unanswered
    if rag_result.get("is_fallback"):
        existing = db.execute(
            "SELECT id, frequency FROM unanswered_questions WHERE bot_id = ? AND question = ?",
            (bot_id, message),
        ).fetchone()
        if existing:
            db.execute("UPDATE unanswered_questions SET frequency = frequency + 1, last_asked_at = ? WHERE id = ?",
                       (datetime.utcnow(), existing["id"]))
        else:
            db.execute("INSERT INTO unanswered_questions (id, bot_id, question) VALUES (?, ?, ?)",
                       (str(uuid.uuid4()), bot_id, message))

    db.commit()
    db.close()

    return jsonify({
        "conversation_id": conversation_id,
        "message_id": assistant_msg_id,
        "answer": rag_result["answer"],
        "sources": rag_result["sources"],
        "confidence": rag_result["confidence"],
        "model_used": rag_result["model_used"],
        "is_fallback": rag_result.get("is_fallback", False),
    })


@chat.route("/api/v1/chat/feedback", methods=["POST"])
def feedback():
    data = request.json
    message_id = data.get("message_id", "")
    fb = data.get("feedback", "")

    db = get_db()
    db.execute("UPDATE messages SET feedback = ?, feedback_reason = ? WHERE id = ?",
               (fb, data.get("reason", ""), message_id))
    db.commit()
    db.close()

    return jsonify({"message": "Feedback recorded"})
@chat.route("/api/v1/lead", methods=["POST"])
def capture_lead():
    data = request.json
    bot_id = data.get("bot_id", "")
    name = data.get("name", "")
    email = data.get("email", "")

    if not bot_id or not email:
        return jsonify({"error": "bot_id and email required"}), 400

    db = get_db()
    db.execute(
        "INSERT INTO leads (id, bot_id, name, email) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), bot_id, name, email),
    )
    db.commit()
    db.close()

    return jsonify({"message": "Lead captured"})