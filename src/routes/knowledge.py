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


def generate_suggested_questions_from_schema(bot_id, schema):
    """Generate 3 suggested questions tailored to a database schema. If the
    schema has customer-scoped tables, questions are phrased in first person
    (e.g. 'Show me my orders') since that's how a real logged-in customer
    will actually use a bot backed by their own account data."""
    try:
        from ..llm.router import llm_router
        from ..llm.base import LLMMessage
        from ..sql.engine import SQLEngine

        schema_text = SQLEngine.schema_to_prompt(schema)
        customer_columns = schema.get("customer_id_columns", {}) or {}

        if customer_columns:
            style_hint = (
                "This data is customer-specific (e.g. orders, tickets, accounts). "
                "Phrase questions in first person, as a logged-in customer would "
                "ask them — e.g. 'What are my recent orders?' or 'Do I have any "
                "open support tickets?'"
            )
        else:
            style_hint = (
                "This is general/shared data, not tied to a specific customer. "
                "Phrase questions a visitor would ask — e.g. 'What products do "
                "you sell?'"
            )

        response = llm_router.generate([
            LLMMessage("system",
                "You are a question generator. Based on the database schema below, "
                "generate exactly 3 short questions a user would likely ask this "
                f"chatbot. {style_hint} Return ONLY a valid JSON array with exactly "
                "3 strings. No explanation, no markdown, no code blocks."),
            LLMMessage("user", f"Database schema:\n\n{schema_text}"),
        ], max_tokens=300, temperature=0.3)

        text = response.content.strip().replace("```json", "").replace("```", "").strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        questions = json.loads(text)
        if isinstance(questions, list) and len(questions) >= 1:
            questions = [str(q).strip() for q in questions[:3] if q]
            print(f"  Auto-generated schema-based questions: {questions}")
            return questions
        return None

    except Exception as e:
        print(f"  Could not generate schema-based questions: {e}")
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

    bot = db.execute("SELECT embedding_provider, embedding_model FROM bots WHERE id = ?", (bot_id,)).fetchone()
    ep = bot["embedding_provider"] if bot else ""
    em = bot["embedding_model"] if bot else ""
    service = IngestionService(embedding_provider=ep, embedding_model=em)
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

    bot_row = db.execute("SELECT embedding_provider, embedding_model FROM bots WHERE id = ?", (bot_id,)).fetchone()
    ep = bot_row["embedding_provider"] if bot_row else ""
    em = bot_row["embedding_model"] if bot_row else ""
    service = IngestionService(embedding_provider=ep, embedding_model=em)
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

        bot_row = db.execute("SELECT embedding_provider, embedding_model FROM bots WHERE id = ?", (bot_id,)).fetchone()
        emb = EmbeddingService(provider=bot_row["embedding_provider"] if bot_row else "", model=bot_row["embedding_model"] if bot_row else "")
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


@knowledge.route("/api/bots/<bot_id>/knowledge/database/upload", methods=["POST"])
def upload_database(bot_id):
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

    try:
        from ..sql.engine import SQLEngine

        engine = SQLEngine(file_path)
        schema = engine.extract_schema(sample_rows=3)

        if schema.get("error"):
            return jsonify({"error": f"Could not read database: {schema['error']}"}), 422

        tables = schema.get("tables", [])
        if not tables:
            return jsonify({"error": "No tables found in database"}), 422

        db = get_db()

        # Save the knowledge source record — NOT ready yet. Stays in
        # "pending_review" until the detected schema (especially which
        # column identifies the customer per table) is confirmed. This is
        # the schema-first rule: never retrieve from unconfirmed data.
        db.execute(
            "INSERT INTO knowledge_sources (id, bot_id, type, name, file_path, db_type, status, ingestion_strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (source_id, bot_id, "database", file.filename, file_path, "sqlite", "pending_review", "text-to-sql"),
        )

        # Save the schema for Text-to-SQL. confirmed=0 means pipeline.py will
        # refuse to run any SQL against this source until /confirm is called.
        db.execute(
            "INSERT INTO sql_sources (id, bot_id, source_id, db_path, db_type, schema_json, table_count, confirmed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), bot_id, source_id, file_path, "sqlite", json.dumps(schema), len(tables), 0),
        )

        # Save a readable glossary (schema-first business glossary)
        db.execute(
            "INSERT INTO business_glossaries (id, bot_id, source_id, table_name, glossary_data, context_text) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), bot_id, source_id, ", ".join(t["name"] for t in tables),
             json.dumps(schema), SQLEngine.schema_to_prompt(schema)),
        )
        db.commit()
        db.close()

        # NOTE: embedding the schema summary + activating this source now
        # happens in /confirm, once the customer-column mapping is reviewed.
        # This is intentional — no retrieval before confirmation.

        return jsonify({
            "source_id": source_id,
            "status": "pending_review",
            "tables_found": len(tables),
            "mode": "text-to-sql",
            "schema": {
                "tables": [
                    {
                        "name": t["name"],
                        "row_count": t.get("row_count", 0),
                        "columns": [c["name"] for c in t["columns"]],
                        "detected_customer_column": schema.get("customer_id_columns", {}).get(t["name"]),
                    }
                    for t in tables
                ],
            },
        })

    except Exception as e:
        print(f"  [DB UPLOAD ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 422


@knowledge.route("/api/bots/<bot_id>/knowledge/database/<source_id>/confirm", methods=["POST"])
def confirm_database_schema(bot_id, source_id):
    """Client/admin reviews the auto-detected schema — especially which
    column identifies the customer in each table — corrects anything wrong,
    and this locks it in permanently. Only after this does the source go
    live for Text-to-SQL and get embedded for RAG (schema-first order:
    detect -> confirm -> THEN retrieval)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.json or {}

    db = get_db()
    row = db.execute(
        "SELECT * FROM sql_sources WHERE source_id = ? AND bot_id = ?",
        (source_id, bot_id),
    ).fetchone()

    if not row:
        db.close()
        return jsonify({"error": "Database source not found"}), 404

    try:
        schema = json.loads(row["schema_json"])
    except Exception:
        db.close()
        return jsonify({"error": "Corrupted schema data"}), 500

    # Expected shape: {"customer_id_columns": {"orders": "customer_id", "products": null, ...}}
    # If the key isn't sent at all, default to keeping whatever was already
    # auto-detected — confirming with no explicit changes should never
    # silently wipe out a working customer-column mapping.
    if "customer_id_columns" in data:
        corrections = data.get("customer_id_columns") or {}
    else:
        corrections = schema.get("customer_id_columns", {}) or {}

    # Apply corrections on top of what was auto-detected. A null/empty value
    # means "this table has no customer column" (admin confirmed shared
    # data). Only tables actually present in the schema are accepted.
    valid_tables = {t["name"] for t in schema.get("tables", [])}
    final_customer_columns = {}
    for table_name, column_name in corrections.items():
        if table_name in valid_tables and column_name:
            final_customer_columns[table_name] = column_name

    schema["customer_id_columns"] = final_customer_columns
    schema_json = json.dumps(schema)

    db.execute(
        "UPDATE sql_sources SET schema_json = ?, confirmed = 1 WHERE source_id = ? AND bot_id = ?",
        (schema_json, source_id, bot_id),
    )
    db.commit()

    # NOW embed the schema summary for RAG and mark the source ready.
    from ..ingestion.chunker import SmartChunker
    from ..embeddings.service import EmbeddingService
    from ..vectordb.store import VectorStore

    ks = db.execute("SELECT file_path FROM knowledge_sources WHERE id = ?", (source_id,)).fetchone()
    file_name = os.path.basename(ks["file_path"]) if ks else "database"

    summary_lines = [f"Database: {file_name}"]
    for t in schema.get("tables", []):
        cols = ", ".join(c["name"] for c in t["columns"])
        summary_lines.append(f"Table {t['name']} has {t.get('row_count', 0)} rows with columns: {cols}")
    summary_text = "\n".join(summary_lines)

    chunker = SmartChunker()
    chunks = chunker.chunk_text(summary_text, {
        "source_id": source_id,
        "source_name": file_name,
        "source_type": "database",
    })

    bot_row = db.execute("SELECT embedding_provider, embedding_model FROM bots WHERE id = ?", (bot_id,)).fetchone()
    emb = EmbeddingService(
        provider=bot_row["embedding_provider"] if bot_row else "",
        model=bot_row["embedding_model"] if bot_row else "",
    )
    vectors = emb.embed_texts([c.content for c in chunks])

    vs = VectorStore()
    collection = f"bot_{bot_id}"
    vs.create_collection(collection, emb.dimension)

    ids = [str(uuid.uuid4()) for _ in chunks]
    payloads = [{"content": c.content, "source_id": source_id, "metadata": c.metadata} for c in chunks]
    vs.upsert(collection, ids, vectors, payloads)

    db.execute(
        "UPDATE knowledge_sources SET status = ?, chunk_count = ? WHERE id = ?",
        ("ready", len(chunks), source_id),
    )

    # Auto-generate suggested questions for the widget welcome screen — same
    # as file/URL uploads get, but tailored to the confirmed schema. Without
    # this, a bot with only a database source shows no quick-click questions.
    questions = generate_suggested_questions_from_schema(bot_id, schema)
    if questions:
        db.execute("UPDATE bots SET suggested_questions = ? WHERE id = ?", (json.dumps(questions), bot_id))
        print(f"  Saved suggested questions for bot {bot_id} (database source)")

    db.commit()
    db.close()

    return jsonify({
        "status": "ready",
        "customer_id_columns": final_customer_columns,
        "chunks_created": len(chunks),
        "suggested_questions": questions or [],
    })