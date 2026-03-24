"""
rizoma-automation / 06_filter_blog.py
======================================
Reads the Ghost blog export from raw_evidence/, extracts all posts tagged
'divulgacion-cientifica', and uses Claude (haiku) to evaluate each one:

  - Is it genuine scientific dissemination for SNII purposes?
  - Score 1–5
  - Recommended action: include / review / exclude
  - Reasoning (brief)
  - A 500-character descripcion in Spanish for the Rizoma form
  - Suggested "dirigido a" audience

Output: raw_evidence/divulgacion_blog_evaluated.json

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...
  python3 scripts/06_filter_blog.py

  Optional flags:
    --limit N     process only first N posts (for testing)
    --resume      skip posts that already have a score (resume interrupted run)
"""

import json
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from auth import load_env

try:
    import anthropic
except ImportError:
    print("Install anthropic: pip3 install anthropic --break-system-packages")
    sys.exit(1)

ROOT        = Path(__file__).parent.parent
RAW_DIR     = ROOT / "raw_evidence"
OUTPUT_FILE = RAW_DIR / "divulgacion_blog_evaluated.json"

GHOST_FILE  = next(RAW_DIR.glob("*.ghost.*.json"), None)

_env        = load_env()
BLOG_DOMAIN = _env.get("BLOG_DOMAIN", "").strip()
if not BLOG_DOMAIN:
    print("  ✗ BLOG_DOMAIN not set in .env (e.g. BLOG_DOMAIN=midominio.com)")
    sys.exit(1)

LIMIT  = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
RESUME = "--resume" in sys.argv

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un evaluador de divulgación científica para el Sistema Nacional de Investigadores (SNII) de México.

Tu tarea es evaluar si un artículo de blog de economía califica como "divulgación científica" según los criterios del SNII:

CALIFICA como divulgación científica si:
- Explica un concepto económico, estadístico, matemático o de ciencias sociales de forma accesible
- Traduce metodologías o resultados de investigación para audiencias no especializadas
- Conecta teoría económica o evidencia empírica con fenómenos del mundo real
- Discute métodos de investigación (econometría, estadística, causalidad, etc.)
- Analiza política económica basándose en evidencia y teoría

NO califica si:
- Es puramente opinión sin sustento teórico o empírico
- Comenta noticias sin explicar conceptos económicos
- Es contenido de productividad personal, motivación o consejos generales de carrera
- Habla de tecnología sin conexión clara con economía o ciencias sociales
- Es un anuncio, presentación de curso o contenido promocional

Responde SIEMPRE en JSON con esta estructura exacta:
{
  "score": <1-5>,
  "recommendation": "<include|review|exclude>",
  "reasoning": "<máximo 150 caracteres en español>",
  "descripcion": "<exactamente entre 400-500 caracteres, en español, descripción para el SNII. Debe describir el contenido del artículo, su relevancia científica y el público al que va dirigido. Sin saltos de línea.>",
  "dirigido_a": "<una opción: Público adulto|Sector estudiantil|Sector empresarial|Otro>"
}

Escala de puntaje:
5 = Excelente divulgación, claramente incluir
4 = Buena divulgación, incluir
3 = Divulgación moderada, revisar
2 = Débil, probablemente excluir
1 = No es divulgación científica, excluir"""

def evaluate_post(client: anthropic.Anthropic, title: str, content: str, url: str) -> dict:
    """Call Claude to evaluate a single blog post."""
    user_msg = f"""Título: {title}
URL: {url}

Contenido (primeros 2000 caracteres):
{content[:2000]}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "score": 0,
            "recommendation": "review",
            "reasoning": f"Parse error: {e}",
            "descripcion": "",
            "dirigido_a": "Público adulto",
            "_raw_response": response.content[0].text[:300] if response else "",
        }
    except Exception as e:
        return {
            "score": 0,
            "recommendation": "review",
            "reasoning": f"API error: {e}",
            "descripcion": "",
            "dirigido_a": "Público adulto",
        }

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Blog Filter — Step 1: AI Evaluation (Claude Haiku)  ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ✗ ANTHROPIC_API_KEY not set.")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if not GHOST_FILE:
        print(f"  ✗ No Ghost export found in {RAW_DIR}")
        sys.exit(1)

    print(f"  → Reading Ghost export: {GHOST_FILE.name}")
    data = json.loads(GHOST_FILE.read_text(encoding="utf-8"))
    db   = data["db"][0]["data"]

    # Build tag → id map
    tags = {t["slug"]: t["id"] for t in db["tags"]}
    div_tag_id = tags.get("divulgacion-cientifica")
    if not div_tag_id:
        print("  ✗ Tag 'divulgacion-cientifica' not found in export")
        sys.exit(1)

    tagged_ids = {pt["post_id"] for pt in db["posts_tags"] if pt["tag_id"] == div_tag_id}
    all_posts  = {p["id"]: p for p in db["posts"]}
    div_posts  = sorted(
        [all_posts[pid] for pid in tagged_ids if pid in all_posts
         and all_posts[pid]["status"] == "published"],
        key=lambda p: p["published_at"] or "",
        reverse=True,
    )

    if LIMIT:
        div_posts = div_posts[:LIMIT]

    print(f"  ✓ Found {len(div_posts)} published posts tagged divulgacion-cientifica")
    if LIMIT:
        print(f"  ⚠ --limit {LIMIT}: processing only first {LIMIT}")

    # Load existing results if resuming
    existing: dict[str, dict] = {}
    if RESUME and OUTPUT_FILE.exists():
        prev = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        existing = {e["slug"]: e for e in prev.get("posts", [])}
        print(f"  → Resuming: {len(existing)} posts already evaluated")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    counts  = {"include": 0, "review": 0, "exclude": 0, "error": 0}

    for i, post in enumerate(div_posts, 1):
        slug       = post["slug"]
        title      = post["title"]
        published  = (post["published_at"] or "")[:10]
        year       = int(published[:4]) if published else 2020
        url        = f"https://{BLOG_DOMAIN}/{slug}/"
        content    = post.get("plaintext") or post.get("html") or ""

        # Skip if already evaluated
        if RESUME and slug in existing:
            entry = existing[slug]
            rec   = entry.get("_ai_recommendation", "review")
            counts[rec if rec in counts else "error"] += 1
            results.append(entry)
            print(f"  [{i:3d}/{len(div_posts)}] ↩  {title[:55]}")
            continue

        print(f"  [{i:3d}/{len(div_posts)}] → {title[:55]}", end="", flush=True)
        evaluation = evaluate_post(client, title, content, url)
        rec = evaluation.get("recommendation", "review")
        score = evaluation.get("score", 0)
        counts[rec if rec in counts else "error"] += 1

        icon = {"include": "✓", "review": "?", "exclude": "✗"}.get(rec, "!")
        print(f"  {icon} [{score}] {rec}")

        entry = {
            # Rizoma fields
            "tipo":       "Blog",
            "anio":       year,
            "rol":        "Actor(a)",
            "titulo":     title,
            "enlace":     url,
            "dirigidoA":  evaluation.get("dirigido_a", "Público adulto"),
            "descripcion": evaluation.get("descripcion", ""),
            # Source metadata
            "slug":       slug,
            "published_at": post["published_at"],
            # AI evaluation
            "_ai_score":          score,
            "_ai_recommendation": rec,
            "_ai_reasoning":      evaluation.get("reasoning", ""),
            # Review tracking
            "_review_status":  rec,      # user can change to: accepted / rejected / pending
            "_review_notes":   "",
            # Upload tracking
            "_meta": {
                "_status":      "pending",
                "_rizoma_id":   None,
                "_uploaded_at": None,
                "_notes":       "",
            },
        }
        results.append(entry)

        # Save after every 5 posts (in case of interruption)
        if i % 5 == 0:
            _save(results)

        time.sleep(0.3)  # gentle rate limiting

    _save(results)

    print(f"\n  ══════════════════ RESULTS ══════════════════")
    print(f"  ✓ include  {counts['include']:>3}  (score 4–5)")
    print(f"  ? review   {counts['review']:>3}  (score 3, or manual check needed)")
    print(f"  ✗ exclude  {counts['exclude']:>3}  (score 1–2)")
    if counts["error"]:
        print(f"  ! error    {counts['error']:>3}")
    print(f"\n  Saved → {OUTPUT_FILE}")
    print(f"  Next: python3 scripts/07_review_blog.py\n")


def _save(results: list):
    include = [r for r in results if r.get("_review_status") == "include"]
    review  = [r for r in results if r.get("_review_status") == "review"]
    exclude = [r for r in results if r.get("_review_status") == "exclude"]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "include_count": len(include),
        "review_count": len(review),
        "exclude_count": len(exclude),
        "posts": results,
    }
    OUTPUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
