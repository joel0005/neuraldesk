"""
One-time helper: confirm an already-uploaded database source so it gets
suggested questions generated and gets embedded, without needing the (not
yet built) review screen in the dashboard.

Run from D:\\chatbot\\ragbase with the server already running:
    python confirm_existing_bot.py YOUR_BOT_ID
"""

import sqlite3
import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print("Usage: python confirm_existing_bot.py YOUR_BOT_ID")
    print("(bot id is visible in the URL when you're on that bot's page, e.g. /bot/63de5423-...)")
    sys.exit(1)

bot_id = sys.argv[1]

conn = sqlite3.connect("db_data/ragbase.db")
row = conn.execute(
    "SELECT source_id, confirmed FROM sql_sources WHERE bot_id = ? ORDER BY created_at DESC LIMIT 1",
    (bot_id,),
).fetchone()
conn.close()

if not row:
    print(f"No database source found for bot_id {bot_id}")
    sys.exit(1)

source_id, confirmed = row
print(f"Found source_id={source_id}, currently confirmed={confirmed}")

url = f"http://localhost:5000/api/bots/{bot_id}/knowledge/database/{source_id}/confirm"
req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print("\nSuccess:")
        print(json.dumps(result, indent=2))
except urllib.error.HTTPError as e:
    print(f"\nRequest failed ({e.code}):")
    print(e.read().decode())