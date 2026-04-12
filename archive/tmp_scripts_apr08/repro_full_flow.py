"""Reproduce the EXACT slack_command_handler flow that crashed for Bobby."""
import os, sys, traceback, sqlite3
from pathlib import Path

env_path = Path("/root/Mining-Gaurdian/.env")
for line in env_path.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

os.chdir("/root/Mining-Gaurdian")
sys.path.insert(0, "/root/Mining-Gaurdian/api")
sys.path.insert(0, "/root/Mining-Gaurdian/core")
sys.path.insert(0, "/root/Mining-Gaurdian/ai")

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

from slack_command_handler import CommandHandler, DB_PATH

handler = CommandHandler.__new__(CommandHandler)

captured = []
def fake_reply(channel, thread_ts, text):
    captured.append(text)
    print(f"[REPLY {len(text)}c] {text[:400]}")
    print()
handler._reply = fake_reply

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn
handler._get_db = get_db

# MONKEY-PATCH the exception handler to also dump traceback
import slack_command_handler as sch
orig_logger = sch.logger
class TBLogger:
    def __getattr__(self, name):
        def wrapper(*args, **kwargs):
            getattr(orig_logger, name)(*args, **kwargs)
            if name == "error":
                traceback.print_exc()
        return wrapper
sch.logger = TBLogger()

print("=" * 60)
print("STEP 1: cmd_ask_llm with Bobby's failing question #1")
print("=" * 60)
try:
    handler.cmd_ask_llm("C0AQ8SE1448", None, "what are my best miners top 5")
except Exception as e:
    print(f"OUTER EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("STEP 2: cmd_ask_llm with Bobby's failing question #2")
print("=" * 60)
try:
    handler.cmd_ask_llm("C0AQ8SE1448", None, "Tell me about my problem miners")
except Exception as e:
    print(f"OUTER EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc()
