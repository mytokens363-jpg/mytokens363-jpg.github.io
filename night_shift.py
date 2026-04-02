"""
Night Shift Article Pipeline — Orchestrator
============================================
Runs nightly. Pulls keywords from queue. Orchestrates Writer, Editor,
and SEO agents via dual LLM routing.

MODEL ROUTING:
  Writer  → Qwen3.5-35B-A3B  (10.0.0.13:8000) — creative generation, faster
  Editor  → Qwen3.5-122B     (10.0.0.13:8000) — high-fidelity quality review
  SEO     → Qwen3.5-122B     (10.0.0.13:8000) — high-fidelity SEO analysis

CONSENSUS RULE: Both Editor AND SEO must output "APPROVE".
If either rejects, their combined revision notes go back to the Writer.
Writer rewrites the full article. Process repeats until both approve
or max revisions (3) is hit — then the article is quarantined.
"""

import json
import datetime
import subprocess
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

MAX_REVISIONS = 3
ARTICLES_PER_NIGHT = 5

# ── Model routing — three separate vLLM endpoints ─────────────────────────────
# Writer:  10.0.0.13 (Rivet2) — Qwen3.5-35B-A3B (faster, creative generation)
# Editor:  10.0.0.21 (Rivet3) — Qwen3.5-122B (high-fidelity review)
# SEO:     10.0.0.21 (Rivet3) — Qwen3.5-122B (high-fidelity review)

WRITER_URL  = "http://10.0.0.13:8000/v1/chat/completions"
EDITOR_URL  = "http://10.0.0.21:8000/v1/chat/completions"
SEO_URL     = "http://10.0.0.21:8000/v1/chat/completions"

WRITER_MODEL  = "Qwen/Qwen3.5-35B-A3B"
EDITOR_MODEL  = "Qwen/Qwen3.5-122B"
SEO_MODEL     = "Qwen/Qwen3.5-122B"

REPO_PATH = Path.home() / "site-repo"
QUEUE_FILE = REPO_PATH / "keyword-queue.md"
PUBLISHING_LOG_FILE = REPO_PATH / "publishing-log.md"
NIGHT_SHIFT_LOG_FILE = REPO_PATH / "night-shift-log.md"
QUARANTINE_DIR = REPO_PATH / "quarantine"

PROMPTS_DIR = Path.home() / "rivet-business" / "prompts"

# ─── Load system prompts ───────────────────────────────────────────────────────

def load_system_prompts() -> dict:
    """Load all agent system prompts from files."""
    writer_prompt_path = PROMPTS_DIR / "writer-system.txt"
    editor_prompt_path = PROMPTS_DIR / "editor-system.txt"
    seo_prompt_path = PROMPTS_DIR / "seo-system.txt"
    article_template_path = PROMPTS_DIR / "article-template.txt"

    writer_system_prompt = writer_prompt_path.read_text()
    editor_system_prompt = editor_prompt_path.read_text()
    seo_system_prompt = seo_prompt_path.read_text()
    article_template = article_template_path.read_text()

    return {
        "writer": writer_system_prompt,
        "editor": editor_system_prompt,
        "seo": seo_system_prompt,
        "template": article_template,
    }


# ─── LLM call ─────────────────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    user_message: str,
    model: str,
    url: str,
    temperature: float = 0.7,
) -> str:
    """
    Call the vLLM endpoint with the specified model and URL.

    Temperature guide:
      0.7 → Writer (creative generation)
      0.3 → Editor / SEO (consistent, reproducible evaluation)
    """
    import requests

    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 8192,
        "temperature": temperature,
    }

    api_response = requests.post(url, json=request_payload, timeout=300)
    api_response.raise_for_status()

    return api_response.json()["choices"][0]["message"]["content"]


def parse_json_from_llm_response(raw_response: str) -> dict:
    """
    Parse JSON from LLM response. Handles markdown code blocks if present.
    """
    cleaned_response = raw_response.strip()

    # Strip markdown code block wrappers if present
    if cleaned_response.startswith("```"):
        lines = cleaned_response.split("\n")
        # Remove first line (```json or ```) and last line (```)
        cleaned_response = "\n".join(lines[1:-1]).strip()

    return json.loads(cleaned_response)


# ─── Keyword queue ─────────────────────────────────────────────────────────────

def get_next_keyword() -> dict | None:
    """
    Pull the next PENDING keyword from keyword-queue.md.
    Format expected in the file:
        - PENDING | cost to replace roof fort lauderdale 2026 | roofing | Fort Lauderdale
    Marks it as IN_PROGRESS and returns the parsed keyword data.
    """
    queue_content = QUEUE_FILE.read_text()
    updated_lines = []
    found_keyword_data = None

    for line in queue_content.splitlines():
        if found_keyword_data is None and line.strip().startswith("- PENDING |"):
            parts = [part.strip() for part in line.split("|")]
            # parts: ["- PENDING", keyword, category, location]
            if len(parts) >= 4:
                found_keyword_data = {
                    "keyword": parts[1],
                    "category": parts[2],
                    "location": parts[3],
                }
                updated_lines.append(line.replace("- PENDING |", "- IN_PROGRESS |", 1))
                continue
        updated_lines.append(line)

    if found_keyword_data:
        QUEUE_FILE.write_text("\n".join(updated_lines))

    return found_keyword_data


def mark_keyword_done(keyword: str, status: str = "PUBLISHED"):
    """Mark a keyword as PUBLISHED or QUARANTINED in the queue file."""
    queue_content = QUEUE_FILE.read_text()
    updated_content = queue_content.replace(
        f"- IN_PROGRESS | {keyword}",
        f"- {status} | {keyword}",
    )
    QUEUE_FILE.write_text(updated_content)


# ─── Writer Agent ──────────────────────────────────────────────────────────────

def write_article(
    keyword: str,
    category: str,
    location: str,
    article_template: str,
    writer_system_prompt: str,
    combined_revision_notes: list | None = None,
    revision_number: int = 0,
) -> str:
    """
    Writer Agent generates or rewrites the article.
    On revision rounds, receives the COMBINED notes from both Editor and SEO.
    Must address every single note in the combined list.
    """

    current_year = datetime.date.today().year

    if combined_revision_notes:
        user_message = f"""REVISION REQUEST — Round {revision_number}

Original keyword: {keyword}
Location: {location}
Category: {category}

The Editor and SEO Analyst reviewed your article and both request revisions.
You must address EVERY note below. Do not skip any.

COMBINED REVISION NOTES FROM EDITOR AND SEO:
{json.dumps(combined_revision_notes, indent=2)}

Use this template:
{article_template}

Return ONLY the complete revised article in markdown with YAML front matter.
No preamble, no commentary, no explanations — just the article.
"""
    else:
        user_message = f"""Write a comprehensive home improvement cost guide article.

Target keyword: {keyword}
Location: {location}
Category: {category}
Year: {current_year}

Use this template EXACTLY:
{article_template}

Return ONLY the complete article in markdown with YAML front matter.
No preamble, no commentary, no explanations — just the article.
"""

    return call_llm(writer_system_prompt, user_message, model=WRITER_MODEL, url=WRITER_URL, temperature=0.7)


# ─── Editor Agent ──────────────────────────────────────────────────────────────

def run_editor_review(
    article_content: str,
    keyword: str,
    editor_system_prompt: str,
) -> dict:
    """
    Editor Agent reviews the article for quality, accuracy, and credibility.
    Returns parsed JSON verdict with revision notes if not approved.
    """

    user_message = f"""Review this article for quality and accuracy.

Target keyword: {keyword}

ARTICLE:
---
{article_content}
---

Provide your review in the JSON format specified in your instructions.
Return ONLY valid JSON — no markdown, no explanation, just the JSON object.
"""

    raw_response = call_llm(editor_system_prompt, user_message, model=EDITOR_MODEL, url=EDITOR_URL, temperature=0.3)
    return parse_json_from_llm_response(raw_response)


# ─── SEO Agent ────────────────────────────────────────────────────────────────

def run_seo_review(
    article_content: str,
    keyword: str,
    seo_system_prompt: str,
) -> dict:
    """
    SEO Agent reviews the article for search optimization.
    Returns parsed JSON verdict with revision notes if not approved.
    """

    user_message = f"""Review this article for SEO optimization.

Target keyword: {keyword}

ARTICLE:
---
{article_content}
---

Provide your review in the JSON format specified in your instructions.
Return ONLY valid JSON — no markdown, no explanation, just the JSON object.
"""

    raw_response = call_llm(seo_system_prompt, user_message, model=SEO_MODEL, url=SEO_URL, temperature=0.3)
    return parse_json_from_llm_response(raw_response)


# ─── Publish ───────────────────────────────────────────────────────────────────

def publish_article(
    article_content: str,
    keyword: str,
    category: str,
    location: str,
    editor_review_result: dict,
    seo_review_result: dict,
):
    """Commit approved article to repo and push to GitHub."""

    current_year = datetime.date.today().year
    url_slug = keyword.lower().replace(" ", "-").replace(",", "")
    article_filename = f"{url_slug}-{current_year}.md"
    article_filepath = REPO_PATH / "content" / category / article_filename

    # Ensure category directory exists
    article_filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write the article file
    article_filepath.write_text(article_content)

    # Git commit and push
    subprocess.run(["git", "add", str(article_filepath)], cwd=REPO_PATH, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add: {keyword} ({location})"],
        cwd=REPO_PATH,
        check=True,
    )
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH, check=True)

    # Append to publishing log
    log_entry = (
        f"| {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"| {keyword} "
        f"| {article_filename} "
        f"| Editor: {editor_review_result.get('overall_score', 'N/A')} "
        f"| SEO: {seo_review_result.get('overall_seo_score', 'N/A')} "
        f"| PUBLISHED |\n"
    )
    with open(PUBLISHING_LOG_FILE, "a") as publishing_log:
        publishing_log.write(log_entry)

    mark_keyword_done(keyword, status="PUBLISHED")
    print(f"  ✅ PUBLISHED: {article_filename}")


# ─── Quarantine ────────────────────────────────────────────────────────────────

def quarantine_article(
    article_content: str,
    keyword: str,
    editor_review_result: dict,
    seo_review_result: dict,
    total_revision_rounds: int,
):
    """
    Article failed to reach consensus after max revisions.
    Save to quarantine folder for human review. Never published automatically.
    """

    QUARANTINE_DIR.mkdir(exist_ok=True)
    timestamp_string = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    quarantine_record = {
        "keyword": keyword,
        "revision_rounds": total_revision_rounds,
        "reason": f"Failed to reach consensus after {total_revision_rounds} revision rounds",
        "editor_final_review": editor_review_result,
        "seo_final_review": seo_review_result,
        "article": article_content,
        "quarantined_at": datetime.datetime.now().isoformat(),
    }

    safe_keyword_slug = keyword[:50].replace(" ", "-").replace("/", "-")
    quarantine_filepath = QUARANTINE_DIR / f"{timestamp_string}_{safe_keyword_slug}.json"
    quarantine_filepath.write_text(json.dumps(quarantine_record, indent=2))

    mark_keyword_done(keyword, status="QUARANTINED")
    print(f"  ⚠️  QUARANTINED: {keyword}")
    print(f"      File: {quarantine_filepath.name}")
    print(f"      Editor score: {editor_review_result.get('overall_score', 'N/A')}")
    print(f"      SEO score: {seo_review_result.get('overall_seo_score', 'N/A')}")


# ─── Main pipeline loop ────────────────────────────────────────────────────────

def run_pipeline_for_keyword(keyword_data: dict, prompts: dict) -> bool:
    """
    Run the full consensus pipeline for a single keyword.

    CONSENSUS RULE: Both Editor AND SEO must output "APPROVE".
    If either rejects → combine all revision notes → send back to Writer.
    Repeat until both approve OR max revisions hit → quarantine.

    Returns True if published, False if quarantined.
    """

    keyword = keyword_data["keyword"]
    category = keyword_data["category"]
    location = keyword_data["location"]

    print(f"\n{'='*60}")
    print(f"📝 STARTING: {keyword}")
    print(f"   Category: {category} | Location: {location}")
    print(f"{'='*60}")

    combined_revision_notes = None
    editor_review_result = {}
    seo_review_result = {}

    for revision_round in range(MAX_REVISIONS + 1):
        round_label = "INITIAL DRAFT" if revision_round == 0 else f"REVISION {revision_round}"
        print(f"\n--- {round_label} ---")

        # ── Step 1: Writer generates or rewrites the article ──────────────────
        print("  ✍️  Writer working...")
        article_content = write_article(
            keyword=keyword,
            category=category,
            location=location,
            article_template=prompts["template"],
            writer_system_prompt=prompts["writer"],
            combined_revision_notes=combined_revision_notes,
            revision_number=revision_round,
        )

        # ── Step 2: Editor reviews the article ────────────────────────────────
        print("  📋 Editor reviewing...")
        editor_review_result = run_editor_review(
            article_content=article_content,
            keyword=keyword,
            editor_system_prompt=prompts["editor"],
        )
        editor_verdict = editor_review_result.get("verdict", "REVISE")
        editor_score = editor_review_result.get("overall_score", "N/A")
        print(f"     Editor verdict: {editor_verdict} (score: {editor_score})")

        # ── Step 3: SEO reviews the article ───────────────────────────────────
        print("  🔍 SEO reviewing...")
        seo_review_result = run_seo_review(
            article_content=article_content,
            keyword=keyword,
            seo_system_prompt=prompts["seo"],
        )
        seo_verdict = seo_review_result.get("verdict", "REVISE")
        seo_score = seo_review_result.get("overall_seo_score", "N/A")
        print(f"     SEO verdict: {seo_verdict} (score: {seo_score})")

        # ── Step 4: Consensus check ────────────────────────────────────────────
        # BOTH Editor AND SEO must approve. Either rejection = revise.
        both_approved = (editor_verdict == "APPROVE" and seo_verdict == "APPROVE")

        if both_approved:
            print("\n  ✅ CONSENSUS REACHED — Both Editor and SEO approved!")
            publish_article(
                article_content=article_content,
                keyword=keyword,
                category=category,
                location=location,
                editor_review_result=editor_review_result,
                seo_review_result=seo_review_result,
            )
            return True

        # ── Step 5: Not approved — check if revisions remain ──────────────────
        if revision_round == MAX_REVISIONS:
            print(f"\n  ❌ MAX REVISIONS ({MAX_REVISIONS}) HIT — Quarantining")
            quarantine_article(
                article_content=article_content,
                keyword=keyword,
                editor_review_result=editor_review_result,
                seo_review_result=seo_review_result,
                total_revision_rounds=revision_round,
            )
            return False

        # ── Step 6: Combine ALL revision notes from both agents ────────────────
        # Writer gets the full combined list — must address every single note.
        editor_revision_notes = editor_review_result.get("revision_notes", [])
        seo_revision_notes = seo_review_result.get("revision_notes", [])

        combined_revision_notes = []

        if editor_verdict == "REVISE":
            for editor_note in editor_revision_notes:
                combined_revision_notes.append(f"[EDITOR] {editor_note}")

        if seo_verdict == "REVISE":
            for seo_note in seo_revision_notes:
                combined_revision_notes.append(f"[SEO] {seo_note}")

        total_notes_count = len(combined_revision_notes)
        rejecting_agents = []
        if editor_verdict == "REVISE":
            rejecting_agents.append("Editor")
        if seo_verdict == "REVISE":
            rejecting_agents.append("SEO")

        print(
            f"\n  🔄 Sending back to Writer — "
            f"{', '.join(rejecting_agents)} rejected. "
            f"{total_notes_count} notes to address."
        )

    return False


# ─── Night shift runner ────────────────────────────────────────────────────────

def run_night_shift():
    """Main loop — runs the full night shift."""

    night_shift_start_time = datetime.datetime.now()
    print(f"\n🌙 NIGHT SHIFT STARTED — {night_shift_start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Target: {ARTICLES_PER_NIGHT} articles\n")

    # Pull latest repo state
    subprocess.run(["git", "pull", "origin", "main"], cwd=REPO_PATH, check=True)

    # Load all system prompts once
    prompts = load_system_prompts()

    night_results = {
        "published": 0,
        "quarantined": 0,
        "errors": 0,
    }

    for article_index in range(ARTICLES_PER_NIGHT):
        print(f"\n{'#'*60}")
        print(f"# ARTICLE {article_index + 1} of {ARTICLES_PER_NIGHT}")
        print(f"{'#'*60}")

        try:
            keyword_data = get_next_keyword()

            if not keyword_data:
                print("⚠️  No more keywords in queue!")
                break

            article_published = run_pipeline_for_keyword(keyword_data, prompts)

            if article_published:
                night_results["published"] += 1
            else:
                night_results["quarantined"] += 1

        except Exception as pipeline_error:
            print(f"  💥 ERROR: {pipeline_error}")
            night_results["errors"] += 1
            continue

    # ── Write night shift summary ──────────────────────────────────────────────
    night_shift_end_time = datetime.datetime.now()
    total_duration = night_shift_end_time - night_shift_start_time
    total_processed = sum(night_results.values())

    summary_text = (
        f"\n## Night Shift Report — {night_shift_start_time.strftime('%Y-%m-%d')}\n\n"
        f"- Duration: {total_duration}\n"
        f"- Published: {night_results['published']}\n"
        f"- Quarantined: {night_results['quarantined']}\n"
        f"- Errors: {night_results['errors']}\n"
        f"- Total processed: {total_processed}\n\n---\n"
    )

    with open(NIGHT_SHIFT_LOG_FILE, "a") as night_log:
        night_log.write(summary_text)

    print(f"\n🌅 NIGHT SHIFT COMPLETE")
    print(f"   Published:   {night_results['published']}")
    print(f"   Quarantined: {night_results['quarantined']}")
    print(f"   Errors:      {night_results['errors']}")
    print(f"   Duration:    {total_duration}")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_night_shift()
