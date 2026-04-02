"""
Night Shift Dashboard — Flask Backend
======================================
Run: python3 dashboard.py
Access: http://localhost:5055

Provides REST API for the pipeline monitoring UI.
Reads live state from ~/site-repo/pipeline-status.json (written by night_shift.py).
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_PATH       = Path.home() / "site-repo"
STATUS_FILE     = REPO_PATH / "pipeline-status.json"
QUARANTINE_DIR  = REPO_PATH / "quarantine"
PUBLISHING_LOG  = REPO_PATH / "publishing-log.md"
QUEUE_FILE      = REPO_PATH / "keyword-queue.md"
CHAT_DIR        = REPO_PATH / "chat-sessions"
PROMPTS_DIR     = Path.home() / "rivet-business" / "prompts"

CHAT_DIR.mkdir(parents=True, exist_ok=True)

# ─── LLM endpoints per agent ──────────────────────────────────────────────────

LLM_ENDPOINTS = {
    "writer": {
        "url":   "http://10.0.0.13:8000/v1/chat/completions",
        "model": "Qwen/Qwen3.5-35B-A3B",
    },
    "editor": {
        "url":   "http://10.0.0.21:8000/v1/chat/completions",
        "model": "Qwen/Qwen3.5-122B",
    },
    "seo": {
        "url":   "http://10.0.0.21:8000/v1/chat/completions",
        "model": "Qwen/Qwen3.5-122B",
    },
}


# ─── UI route ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── Pipeline status ──────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    if STATUS_FILE.exists():
        return jsonify(json.loads(STATUS_FILE.read_text()))
    return jsonify({
        "run_active":       False,
        "run_started":      None,
        "articles_target":  0,
        "articles_done":    0,
        "current_article":  None,
        "results":          [],
        "last_updated":     None,
    })


# ─── Keyword queue ─────────────────────────────────────────────────────────────

@app.route("/api/queue")
def api_queue():
    if not QUEUE_FILE.exists():
        return jsonify([])

    items = []
    for line in QUEUE_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        parts = [p.strip() for p in stripped[2:].split("|")]
        if len(parts) >= 4:
            items.append({
                "status":   parts[0],
                "keyword":  parts[1],
                "category": parts[2],
                "location": parts[3],
                "notes":    parts[4].replace("HUMAN_NOTES:", "").strip() if len(parts) > 4 else "",
            })
    return jsonify(items)


# ─── Quarantine list ───────────────────────────────────────────────────────────

@app.route("/api/quarantine")
def api_quarantine():
    if not QUARANTINE_DIR.exists():
        return jsonify([])

    items = []
    for filepath in sorted(QUARANTINE_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(filepath.read_text())
            items.append({
                "id":              filepath.stem,
                "keyword":         data.get("keyword"),
                "category":        data.get("category", ""),
                "location":        data.get("location", ""),
                "revision_rounds": data.get("revision_rounds"),
                "reason":          data.get("reason"),
                "quarantined_at":  data.get("quarantined_at"),
                "editor_score":    data.get("editor_final_review", {}).get("overall_score", "N/A"),
                "seo_score":       data.get("seo_final_review", {}).get("overall_seo_score", "N/A"),
            })
        except Exception:
            continue
    return jsonify(items)


# ─── Single quarantine record ──────────────────────────────────────────────────

@app.route("/api/quarantine/<item_id>")
def api_quarantine_item(item_id):
    filepath = QUARANTINE_DIR / f"{item_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify(json.loads(filepath.read_text()))


# ─── Delete quarantined article ────────────────────────────────────────────────

@app.route("/api/quarantine/<item_id>/delete", methods=["POST"])
def api_quarantine_delete(item_id):
    filepath = QUARANTINE_DIR / f"{item_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404
    filepath.unlink()
    return jsonify({"success": True})


# ─── Rewrite quarantined article (re-queue with human notes) ──────────────────

@app.route("/api/quarantine/<item_id>/rewrite", methods=["POST"])
def api_quarantine_rewrite(item_id):
    """
    Put a quarantined article back into the queue with human notes prepended.
    Pipeline will pick it up on the next run and address the human notes first.
    """
    filepath = QUARANTINE_DIR / f"{item_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404

    data      = json.loads(filepath.read_text())
    keyword   = data.get("keyword", "")
    category  = data.get("category", "general")
    location  = data.get("location", "Florida")
    notes     = request.json.get("notes", "").strip() if request.json else ""

    # Build queue entry — include human notes if provided
    new_entry = f"- PENDING | {keyword} | {category} | {location}"
    if notes:
        new_entry += f" | HUMAN_NOTES: {notes}"

    queue_text = QUEUE_FILE.read_text() if QUEUE_FILE.exists() else "## Queue\n\n"

    # Inject at top of queue list (highest priority)
    if "## Queue" in queue_text:
        queue_text = queue_text.replace("## Queue\n", f"## Queue\n{new_entry}\n", 1)
    else:
        queue_text += f"\n{new_entry}\n"

    QUEUE_FILE.write_text(queue_text)
    filepath.unlink()

    return jsonify({"success": True, "keyword": keyword})


# ─── Chat with an agent ────────────────────────────────────────────────────────

@app.route("/api/chat/<agent>", methods=["GET"])
def api_chat_get(agent):
    if agent not in LLM_ENDPOINTS:
        return jsonify({"error": "Unknown agent"}), 400

    chat_file = CHAT_DIR / f"{agent}-chat.json"
    if chat_file.exists():
        return jsonify(json.loads(chat_file.read_text()))
    return jsonify({"messages": []})


@app.route("/api/chat/<agent>", methods=["POST"])
def api_chat_post(agent):
    """Send a message to an agent and get a reply."""
    if agent not in LLM_ENDPOINTS:
        return jsonify({"error": "Unknown agent"}), 400

    user_message = (request.json or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Load chat history
    chat_file = CHAT_DIR / f"{agent}-chat.json"
    history   = json.loads(chat_file.read_text()) if chat_file.exists() else {"messages": []}

    # Load agent system prompt
    prompt_file   = PROMPTS_DIR / f"{agent}-system.txt"
    system_prompt = prompt_file.read_text() if prompt_file.exists() else f"You are the {agent} agent for the Night Shift article pipeline."

    # Build message list for LLM (keep last 10 turns for context)
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in history["messages"][-10:]:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    llm_messages.append({"role": "user", "content": user_message})

    # Call vLLM
    import requests as req
    endpoint = LLM_ENDPOINTS[agent]
    try:
        response = req.post(
            endpoint["url"],
            json={
                "model":       endpoint["model"],
                "messages":    llm_messages,
                "max_tokens":  2048,
                "temperature": 0.7,
            },
            timeout=120,
        )
        response.raise_for_status()
        assistant_reply = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    # Persist conversation
    now = datetime.now().isoformat()
    history["messages"].append({"role": "user",      "content": user_message,    "ts": now})
    history["messages"].append({"role": "assistant", "content": assistant_reply, "ts": now})
    chat_file.write_text(json.dumps(history, indent=2))

    return jsonify({"reply": assistant_reply, "messages": history["messages"]})


@app.route("/api/chat/<agent>/clear", methods=["POST"])
def api_chat_clear(agent):
    chat_file = CHAT_DIR / f"{agent}-chat.json"
    if chat_file.exists():
        chat_file.unlink()
    return jsonify({"success": True})


# ─── Publishing log ────────────────────────────────────────────────────────────

@app.route("/api/published")
def api_published():
    if not PUBLISHING_LOG.exists():
        return jsonify([])

    entries = []
    for line in PUBLISHING_LOG.read_text().splitlines():
        if not line.startswith("| ") or "----" in line or "Date" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 5:
            entries.append({
                "date":         parts[0],
                "keyword":      parts[1],
                "file":         parts[2],
                "editor_score": parts[3],
                "seo_score":    parts[4],
                "status":       parts[5] if len(parts) > 5 else "PUBLISHED",
            })
    return jsonify(list(reversed(entries)))


# ─── Add keyword to queue ──────────────────────────────────────────────────────

@app.route("/api/queue/add", methods=["POST"])
def api_queue_add():
    data     = request.json or {}
    keyword  = data.get("keyword", "").strip()
    category = data.get("category", "general").strip()
    location = data.get("location", "Florida").strip()

    if not keyword:
        return jsonify({"error": "keyword required"}), 400

    queue_text = QUEUE_FILE.read_text() if QUEUE_FILE.exists() else "## Queue\n\n"
    new_entry  = f"- PENDING | {keyword} | {category} | {location}"

    if "## Queue" in queue_text:
        queue_text = queue_text.replace("## Queue\n", f"## Queue\n{new_entry}\n", 1)
    else:
        queue_text += f"\n{new_entry}\n"

    QUEUE_FILE.write_text(queue_text)
    return jsonify({"success": True})


# ─── Run pipeline manually ─────────────────────────────────────────────────────

@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    """Trigger a pipeline run in the background (non-blocking)."""
    script = Path.home() / "rivet-business" / "night_shift.py"
    try:
        subprocess.Popen(
            ["python3", str(script)],
            stdout=open(REPO_PATH / "manual-run.log", "a"),
            stderr=subprocess.STDOUT,
        )
        return jsonify({"success": True, "message": "Pipeline started"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🌙 Night Shift Dashboard")
    print("   Access: http://localhost:5055")
    app.run(host="0.0.0.0", port=5055, debug=False)
