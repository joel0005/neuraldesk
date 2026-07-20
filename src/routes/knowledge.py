"""Knowledge Routes — upload files, add URLs, manage sources."""

import os
import uuid
import json
from flask import Blueprint, request, jsonify
from ..models.database import get_db
from ..ingestion.service import IngestionService
from ..ingestion.parsers import parse_file
from ..config import config
from .auth import get_current_user

knowledge = Blueprint("knowledge", __name__)


def generate_suggested_questions(bot_id, content):
    """Use LLM to auto-generate suggested questions from uploaded content."""
    try:
        from ..llm.router import llm_router
        from ..llm.base import LLMMessage

        sample = content[:3000]
        response = llm_router.generate([
            LLMMessage("system", "You are a question generator. Based on the document content below, generate exactly 3 short questions that a user would likely ask about this document. Return ONLY a valid JSON array with exactly 3 strings. No explanation, no markdown, no code blocks. Example format: [\"Question one?\", \"Question two?\", \"Question three?\"]"),
            LLMMessage("user", f"Document content:\n\n{sample}"),
        ], max_tokens=300, temperature=0.3)

        text = response.content.strip()
        # Clean up common LLM formatting issues
        text = text.replace("```json", "").replace("```", "").strip()
        # Find the JSON array in the response
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        questions = json.loads(text)

        if isinstance(questions, list) and len(questions) >= 1:
            # Take only first 3
            questions = [str(q).strip() for q in questions[:3] if q]
            print(f"  Auto-generated questions: {questions}")
            return questions
        else:
            print(f"  Question generation returned invalid format: {text}")
            return None

    except json.JSONDecodeError as e:
        print(f"  Could not parse questions JSON: {e}")
        print(f"  Raw response: {text}")
        return None
    except Exception as e:
        print(f"  Could not generate questions: {e}")
        return None

@knowledge.route("/api/bots/<bot_id>/knowledge/file", methods=["POST"])
def upload_file(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    source_id = str(uuid.uuid4())
    upload_dir = os.path.join(config.UPLOAD_DIR, bot_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{source_id}_{file.filename}")
    file.save(file_path)

    db = get_db()
    db.execute(
        "INSERT INTO knowledge_sources (id, bot_id, type, name, file_path, file_type, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source_id, bot_id, "file", file.filename, file_path, os.path.splitext(file.filename)[1].lower(), "processing"),
    )
    db.commit()

    service = IngestionService()
    result = service.ingest_file(file_path, bot_id, source_id)

    if result["success"]:
        db.execute(
            "UPDATE knowledge_sources SET status = ?, chunk_count = ?, ingestion_strategy = ? WHERE id = ?",
            ("ready", result["chunks_created"], result["strategy"], source_id),
        )

        # Auto-generate suggested questions
        parsed = parse_file(file_path)
        content = parsed.get("content", "")
        if content:
            questions = generate_suggested_questions(bot_id, content)
            if questions:
                db.execute("UPDATE bots SET suggested_questions = ? WHERE id = ?", (json.dumps(questions), bot_id))
                print(f"  Saved questions for bot {bot_id}")
            else:
                # Fallback: generate simple questions from content
                lines = [l.strip() for l in content.split("\n") if len(l.strip()) > 20][:3]
                fallback = [f"Tell me about {l[:50]}?" for l in lines]
                if fallback:
                    db.execute("UPDATE bots SET suggested_questions = ? WHERE id = ?", (json.dumps(fallback), bot_id))
                    print(f"  Saved fallback questions for bot {bot_id}")
    else:
        db.execute(
            "UPDATE knowledge_sources SET status = ?, error_message = ? WHERE id = ?",
            ("failed", result["error"], source_id),
        )

    db.commit()
    db.close()

    if result["success"]:
        return jsonify({"source_id": source_id, "status": "ready", "chunks_created": result["chunks_created"]})
    else:
        return jsonify({"error": result["error"]}), 422


@knowledge.route("/api/bots/<bot_id>/knowledge/url", methods=["POST"])
def add_url(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.json
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "URL required"}), 400

    source_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO knowledge_sources (id, bot_id, type, name, url, status) VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, bot_id, "url", url, url, "processing"),
    )
    db.commit()

    service = IngestionService()
    result = service.ingest_url(url, bot_id, source_id)

    if result["success"]:
        db.execute("UPDATE knowledge_sources SET status = ?, chunk_count = ? WHERE id = ?", ("ready", result["chunks_created"], source_id))
    else:
        db.execute("UPDATE knowledge_sources SET status = ?, error_message = ? WHERE id = ?", ("failed", result["error"], source_id))

    db.commit()
    db.close()

    if result["success"]:
        return jsonify({"source_id": source_id, "status": "ready", "chunks_created": result["chunks_created"]})
    else:
        return jsonify({"error": result["error"]}), 422


@knowledge.route("/api/bots/<bot_id>/knowledge", methods=["GET"])
def list_sources(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    db = get_db()
    sources = db.execute("SELECT * FROM knowledge_sources WHERE bot_id = ?", (bot_id,)).fetchall()
    db.close()

    return jsonify([dict(s) for s in sources])


@knowledge.route("/api/bots/<bot_id>/knowledge/<source_id>", methods=["DELETE"])
def delete_source(bot_id, source_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    service = IngestionService()
    service.delete_source(bot_id, source_id)

    db = get_db()
    db.execute("DELETE FROM knowledge_sources WHERE id = ? AND bot_id = ?", (source_id, bot_id))
    db.commit()
    db.close()
    

    

    return jsonify({"message": "Source deleted"})


@knowledge.route("/api/bots/<bot_id>/knowledge/database", methods=["POST"])
def connect_database(bot_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.json
    db_type = data.get("db_type", "")
    if not db_type:
        return jsonify({"error": "Database type required"}), 400

    source_id = str(uuid.uuid4())

    try:
        from ..ingestion.db_connectors import create_connector
        connector = create_connector(
            db_type=db_type,
            host=data.get("host", "localhost"),
            port=data.get("port", 3306),
            database=data.get("database", ""),
            user=data.get("username", ""),
            password=data.get("password", ""),
        )
        result = connector.test_connection()

        if not result["success"]:
            return jsonify({"error": f"Connection failed: {result.get('error', '')}"}), 422

        tables = result.get("tables", [])
        total_rows = result.get("total_rows", 0)

        all_rows = []
        for table_info in tables:
            sample = connector.get_sample(table_info["name"], limit=100)
            if sample["success"] and sample.get("rows"):
                for row in sample["rows"]:
                    if isinstance(row, dict):
                        parts = [f"{k}: {v}" for k, v in row.items() if v is not None]
                        all_rows.append(", ".join(parts))

        connector.close()

        if not all_rows:
            return jsonify({"error": "No data found in database"}), 422

        db = get_db()
        db.execute(
            "INSERT INTO knowledge_sources (id, bot_id, type, name, db_type, status) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, bot_id, "database", f"{db_type}: {data.get('database', '')}", db_type, "processing"),
        )
        db.commit()

        from ..ingestion.chunker import SmartChunker
        from ..embeddings.service import EmbeddingService
        from ..vectordb.store import VectorStore
        import uuid as uuid_mod

        chunker = SmartChunker()
        text = "\n".join(all_rows)
        chunks = chunker.chunk_text(text, {"source_id": source_id, "source_name": f"{db_type} database", "source_type": "database"})

        emb = EmbeddingService()
        vectors = emb.embed_texts([c.content for c in chunks])

        vs = VectorStore()
        collection = f"bot_{bot_id}"
        vs.create_collection(collection, emb.dimension)

        ids = [str(uuid_mod.uuid4()) for _ in chunks]
        payloads = [{"content": c.content, "source_id": source_id, "metadata": c.metadata} for c in chunks]
        vs.upsert(collection, ids, vectors, payloads)

        db.execute(
            "UPDATE knowledge_sources SET status = ?, chunk_count = ? WHERE id = ?",
            ("ready", len(chunks), source_id),
        )
        db.commit()
        db.close()

        return jsonify({
            "source_id": source_id,
            "status": "ready",
            "tables_found": len(tables),
            "total_rows": total_rows,
            "chunks_created": len(chunks),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 422