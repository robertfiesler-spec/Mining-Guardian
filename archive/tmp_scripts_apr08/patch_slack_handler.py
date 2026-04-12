"""Patch slack_command_handler.py cmd_ask_llm to be defensive about API errors."""
from pathlib import Path

SRC = Path("/Users/BigBobby/tmp_scripts/slack_handler.py")
src = SRC.read_text()

OLD = '''            from llm_analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()

            # Prefer Claude API for conversational questions (faster, smarter)
            import os
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            if anthropic_key:
                resp = requests.post("https://api.anthropic.com/v1/messages", json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 800,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}]
                }, headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }, timeout=30)
                answer = resp.json()["content"][0]["text"]
            else:
                # Fallback to local Ollama
                answer, _ = analyzer._query_llm(f"{system}\\n\\n{prompt}")

            self._reply(channel, thread_ts, f"*🧠 Mining Guardian AI:*\\n{answer[:2000]}")

        except Exception as e:
            logger.error("LLM query failed: %s", e)
            self._reply(channel, thread_ts, f"❌ LLM query failed: {e}")'''

NEW = '''            from llm_analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()

            # Prefer Claude API for conversational questions (faster, smarter).
            # Defensive: retry once on transient errors, fall back to Ollama on
            # repeated failure, surface useful error messages instead of opaque KeyErrors.
            import os
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            answer = None
            api_error = None
            if anthropic_key:
                for attempt in (1, 2):
                    try:
                        resp = requests.post("https://api.anthropic.com/v1/messages", json={
                            "model": "claude-sonnet-4-6",
                            "max_tokens": 800,
                            "system": system,
                            "messages": [{"role": "user", "content": prompt}]
                        }, headers={
                            "x-api-key": anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json"
                        }, timeout=45)
                        body = resp.json()
                        if resp.status_code == 200 and "content" in body and body["content"]:
                            answer = body["content"][0].get("text", "")
                            break
                        # Non-success or malformed response — log and possibly retry
                        err_type = body.get("error", {}).get("type", f"http_{resp.status_code}")
                        err_msg  = body.get("error", {}).get("message", str(body)[:200])
                        api_error = f"{err_type}: {err_msg}"
                        logger.warning("Claude API attempt %d failed: %s", attempt, api_error)
                        if attempt == 1:
                            time.sleep(1.0)
                    except requests.exceptions.RequestException as req_err:
                        api_error = f"request_exception: {req_err}"
                        logger.warning("Claude API attempt %d network error: %s", attempt, req_err)
                        if attempt == 1:
                            time.sleep(1.0)
            if answer is None:
                # Fallback to local Ollama
                logger.info("Falling back to local Ollama (Claude error: %s)", api_error)
                try:
                    answer, _ = analyzer._query_llm(f"{system}\\n\\n{prompt}")
                except Exception as ollama_err:
                    raise RuntimeError(
                        f"Both LLMs unavailable. Claude: {api_error}. Ollama: {ollama_err}"
                    )

            self._reply(channel, thread_ts, f"*🧠 Mining Guardian AI:*\\n{answer[:2000]}")

        except Exception as e:
            logger.error("LLM query failed: %s", e, exc_info=True)
            self._reply(channel, thread_ts, f"❌ LLM query failed: {e}")'''

if OLD not in src:
    print("FAILED: old block not found verbatim.")
    raise SystemExit(1)

new_src = src.replace(OLD, NEW)
SRC.write_text(new_src)
print(f"PATCHED locally: {SRC}")
print(f"  {len(src)} -> {len(new_src)} chars  (+{len(new_src)-len(src)})")
