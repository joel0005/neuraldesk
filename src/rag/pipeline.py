"""RAG Pipeline — fixed version with debug prints."""

import time
from ..llm.base import LLMMessage
from ..llm.router import llm_router
from ..embeddings.service import EmbeddingService
from ..vectordb.store import VectorStore


class RAGPipeline:

    def __init__(self, bot_config: dict):
        self.config = bot_config
        self.embedding = EmbeddingService(
            provider=bot_config.get("embedding_provider") or "",
            model=bot_config.get("embedding_model") or "",
        )
        self.vector_store = VectorStore()

    def run(self, query: str, conversation_history: list = None) -> dict:
        start_time = time.time()
        conversation_history = conversation_history or []
        bot = self.config

        # Try Text-to-SQL first if this bot has database sources
        sql_result = self._try_sql(query, bot, start_time)
        if sql_result is not None:
            return sql_result

        # Safe get values (handle None properly)
        top_k = 3
        threshold = 0.0  # Always return results, let the LLM decide
        confidence_threshold = bot.get("confidence_threshold") or 0.1
        fallback_msg = bot.get("fallback_message") or "I am not sure about that. Would you like to speak with a human?"

        # Step 1: Guardrails
        blocked_words = bot.get("blocked_words") or "[]"
        if isinstance(blocked_words, str):
            import json
            try:
                blocked_words = json.loads(blocked_words)
            except Exception:
                blocked_words = []

        for word in blocked_words:
            if isinstance(word, str) and word.lower() in query.lower():
                return self._response(fallback_msg, is_fallback=True, start=start_time)

        # Step 2: Search vector DB
        collection = f"bot_{bot['id']}"
        print(f"  [RAG] Searching collection: {collection}")
        print(f"  [RAG] Query: {query}")
        print(f"  [RAG] Top K: {top_k}, Threshold: {threshold}")

        query_vector = self.embedding.embed_query(query)
        results = self.vector_store.search(collection, query_vector, top_k=int(top_k))

        print(f"  [RAG] Search returned {len(results)} results")
        for r in results:
            print(f"    Score: {r.score:.3f} | Content: {r.content[:100]}...")

        # Step 3: Filter by threshold
        filtered = [r for r in results if r.score >= float(threshold)]
        
        print(f"  [RAG] After threshold filter: {len(filtered)} results")

        if not filtered:
            return self._response(fallback_msg, is_fallback=True, start=start_time)

        # Step 4: Build prompt with context
        context_parts = []
        for i, chunk in enumerate(filtered):
            source_name = chunk.metadata.get("source_name", f"Source {i+1}")
            page = chunk.metadata.get("page_number", "")
            page_info = f" (Page {page})" if page else ""
            context_parts.append(f"[Source: {source_name}{page_info}]\n{chunk.content}")

        context = "\n\n---\n\n".join(context_parts)

        persona = bot.get("persona_name") or "Assistant"
        system_prompt = bot.get("system_prompt") or f"You are {persona}, a helpful assistant."
        system_prompt += f"\n\nYou have access to the following documents. Use ONLY this information to answer."
        system_prompt += f"\n\n{context}"
        system_prompt += "\n\nINSTRUCTIONS:"
        system_prompt += "\n- Answer the user's question using ONLY the information above."
        system_prompt += "\n- If the answer is in the documents, give a clear detailed response."
        system_prompt += "\n- Format with bullet points (•) when listing multiple items."
        system_prompt += "\n- If the question has NOTHING to do with the documents, say: 'I can only answer questions related to my knowledge base.'"
        system_prompt += "\n- NEVER make up information not in the documents."
        system_prompt += "\n- Do NOT ask the user to provide context or documents."
        system_prompt += "\n- Do NOT mention filenames or source names."

        messages = [LLMMessage(role="system", content=system_prompt)]

        for msg in conversation_history[-6:]:
            messages.append(LLMMessage(role=msg.get("role", "user"), content=msg.get("content", "")))

        messages.append(LLMMessage(role="user", content=query))

        # Step 5: Generate with LLM
        try:
            print(f"  [RAG] Calling LLM: {bot.get('llm_provider')}/{bot.get('llm_model')}")
            llm_response = llm_router.generate(
                messages=messages,
                provider=bot.get("llm_provider") or "ollama",
                model=bot.get("llm_model") or "gemma3:latest",
                temperature=float(bot.get("temperature") or 0.7),
                max_tokens=2048,
                api_key=bot.get("llm_api_key") or "",
            )
            print(f"  [RAG] LLM responded in {llm_response.latency_ms}ms")
        except Exception as e:
            print(f"  [RAG] LLM error: {e}")
            return self._response(f"Error generating response: {str(e)}", is_fallback=True, start=start_time)

        # Step 6: Build sources
        sources = []
        seen = set()
        for chunk in filtered:
            sid = chunk.metadata.get("source_id", chunk.id)
            if sid not in seen:
                seen.add(sid)
                sources.append({
                    "source_name": chunk.metadata.get("source_name", "Unknown"),
                    "source_type": chunk.metadata.get("source_type", "document"),
                    "page_number": chunk.metadata.get("page_number"),
                    "score": round(chunk.score, 3),
                    "snippet": chunk.content[:200],
                })

        avg_score = sum(r.score for r in filtered) / len(filtered)
        confidence = round(min(max(avg_score, 0.0), 1.0), 2)

        latency = int((time.time() - start_time) * 1000)

        return {
            "answer": llm_response.content,
            "sources": sources,
            "confidence": confidence,
            "model_used": llm_response.model,
            "provider_used": llm_response.provider,
            "tokens_input": llm_response.tokens_input,
            "tokens_output": llm_response.tokens_output,
            "latency_ms": latency,
            "is_fallback": False,
        }
    def _try_sql(self, query: str, bot: dict, start_time: float):
        """If the bot has a SQL source, try answering with Text-to-SQL. Returns None to fall back to RAG."""
        import json
        from ..models.database import get_db
        from ..sql.engine import SQLEngine

        try:
            db = get_db()
            row = db.execute(
                "SELECT db_path, schema_json FROM sql_sources WHERE bot_id = ? ORDER BY created_at DESC LIMIT 1",
                (bot["id"],),
            ).fetchone()
            db.close()
        except Exception as e:
            print(f"  [SQL] Could not load sql_sources: {e}")
            return None

        if not row:
            return None

        print(f"  [SQL] Database source found, trying Text-to-SQL")

        try:
            schema = json.loads(row["schema_json"])
        except Exception:
            return None

        engine = SQLEngine(row["db_path"])

        gen = engine.generate_sql(query, schema, llm_router, bot)
        if not gen["success"]:
            print(f"  [SQL] {gen['error']} — falling back to RAG")
            return None

        sql = gen["sql"]
        print(f"  [SQL] Generated: {sql}")

        exec_result = engine.run_query(sql)
        if not exec_result["success"]:
            print(f"  [SQL] Execution failed: {exec_result['error']} — falling back to RAG")
            return None

        rows = exec_result["rows"]
        print(f"  [SQL] Returned {len(rows)} rows")

        if not rows:
            fallback_msg = bot.get("fallback_message") or "I could not find any matching records."
            return self._response(fallback_msg, is_fallback=True, start=start_time)

        results_text = SQLEngine.rows_to_text(exec_result["columns"], rows)

        persona = bot.get("persona_name") or "Assistant"
        system_prompt = bot.get("system_prompt") or f"You are {persona}, a helpful assistant."
        system_prompt += (
            "\n\nThe user asked a question about their data. Here are the exact results from the database:\n\n"
            f"{results_text}\n\n"
            "INSTRUCTIONS:\n"
            "- Answer using ONLY these results.\n"
            "- Present the information clearly and naturally.\n"
            "- Use bullet points (•) when listing multiple items.\n"
            "- Do NOT mention SQL, queries, tables, or databases.\n"
            "- Do NOT make up any information not in the results above."
        )

        try:
            llm_response = llm_router.generate(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=query),
                ],
                provider=bot.get("llm_provider") or "ollama",
                model=bot.get("llm_model") or "gemma3:latest",
                temperature=float(bot.get("temperature") or 0.7),
                max_tokens=2048,
                api_key=bot.get("llm_api_key") or "",
            )
        except Exception as e:
            print(f"  [SQL] LLM formatting error: {e}")
            return None

        latency = int((time.time() - start_time) * 1000)

        return {
            "answer": llm_response.content,
            "sources": [{
                "source_name": "Database",
                "source_type": "database",
                "page_number": None,
                "score": 1.0,
                "snippet": results_text[:200],
            }],
            "confidence": 1.0,
            "model_used": llm_response.model,
            "provider_used": llm_response.provider,
            "tokens_input": llm_response.tokens_input,
            "tokens_output": llm_response.tokens_output,
            "latency_ms": latency,
            "is_fallback": False,
            "sql_used": sql,
        }

    def _response(self, answer: str, is_fallback: bool = False, start: float = 0) -> dict:
        return {
            "answer": answer,
            "sources": [],
            "confidence": 0.0,
            "model_used": "",
            "provider_used": "",
            "tokens_input": 0,
            "tokens_output": 0,
            "latency_ms": int((time.time() - start) * 1000) if start else 0,
            "is_fallback": is_fallback,
        }