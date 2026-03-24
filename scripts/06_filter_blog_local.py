"""
rizoma-automation / 06_filter_blog_local.py
============================================
LOCAL filtering (no API needed). Reads Ghost export, shows all 97 posts,
lets you interactively select which ones are divulgación científica worth
uploading to SNII.

Reads:   raw_evidence/*.ghost.*.json
Writes:  raw_evidence/divulgacion_blog_filtered.json

Usage:
  python3 scripts/06_filter_blog_local.py

Then:
  python3 scripts/07_review_blog.py
"""

import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from auth import load_env

ROOT        = Path(__file__).parent.parent
RAW_DIR     = ROOT / "raw_evidence"
OUTPUT_FILE = RAW_DIR / "divulgacion_blog_filtered.json"

GHOST_FILE  = next(RAW_DIR.glob("*.ghost.*.json"), None)

_env        = load_env()
BLOG_DOMAIN = _env.get("BLOG_DOMAIN", "").strip()
if not BLOG_DOMAIN:
    print("  ✗ BLOG_DOMAIN not set in .env (e.g. BLOG_DOMAIN=midominio.com)")
    sys.exit(1)

# Keywords that suggest strong scientific/academic content
SCI_KEYWORDS = {
    "economía", "estadística", "econometría", "regresión", "análisis",
    "causalidad", "metodología", "investigación", "teoría", "modelo",
    "hipótesis", "datos", "evidencia", "ciencia", "método", "variable",
    "estimador", "significancia", "p-value", "correlación", "covariate",
    "sesgo", "poder", "muestra", "experimental", "control", "panel",
    "distribución", "probabilidad", "inferencia", "estimación",
    "matemática", "algoritmo", "inteligencia artificial", "machine learning",
    "estadístico", "cuantitativo", "cualitativo", "benchmarks",
}

def score_post(title: str, excerpt: str, content: str) -> int:
    """Heuristic: how likely is this genuine divulgación científica (1–5)?"""
    text = f"{title} {excerpt} {content}".lower()

    # Count science keywords
    keywords_found = sum(1 for kw in SCI_KEYWORDS if kw in text)

    # Penalize for opinion/lifestyle keywords
    opinion_words = {"opinión", "reflexión", "thoughts", "mi consejo", "deberías",
                     "nft", "crypto", "dinero", "viajes", "productividad personal"}
    opinion_count = sum(1 for w in opinion_words if w in text)

    # Base score on keyword density
    if keywords_found >= 5:
        score = 5
    elif keywords_found >= 3:
        score = 4
    elif keywords_found >= 1:
        score = 3
    else:
        score = 2

    # Adjust for opinion content
    if opinion_count > 2:
        score = max(1, score - 2)
    elif opinion_count > 0:
        score = max(2, score - 1)

    return min(5, max(1, score))

def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Blog Filter — LOCAL (no API needed)                 ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    if not GHOST_FILE:
        print(f"  ✗ No Ghost export found in {RAW_DIR}")
        sys.exit(1)

    print(f"  → Reading: {GHOST_FILE.name}")
    data = json.loads(GHOST_FILE.read_text(encoding="utf-8"))
    db   = data["db"][0]["data"]

    tags = {t["slug"]: t["id"] for t in db["tags"]}
    div_tag_id = tags.get("divulgacion-cientifica")
    if not div_tag_id:
        print("  ✗ Tag 'divulgacion-cientifica' not found")
        sys.exit(1)

    tagged_ids = {pt["post_id"] for pt in db["posts_tags"] if pt["tag_id"] == div_tag_id}
    all_posts  = {p["id"]: p for p in db["posts"]}
    posts      = sorted(
        [all_posts[pid] for pid in tagged_ids if pid in all_posts
         and all_posts[pid]["status"] == "published"],
        key=lambda p: p["published_at"] or "",
        reverse=True,
    )

    print(f"  ✓ Found {len(posts)} published posts\n")

    # Score each post
    scored = []
    for post in posts:
        title    = post["title"]
        excerpt  = post.get("custom_excerpt", "")
        content  = post.get("plaintext", "")
        year     = int((post.get("published_at") or "")[:4]) if post.get("published_at") else 2020
        slug     = post["slug"]
        url      = f"https://{BLOG_DOMAIN}/{slug}/"

        score = score_post(title, excerpt, content)
        scored.append({
            "score": score,
            "title": title,
            "excerpt": excerpt,
            "year": year,
            "slug": slug,
            "url": url,
            "content_sample": content[:200],
            "post": post,
        })

    # Sort by score (descending) then year (newest first)
    scored.sort(key=lambda x: (-x["score"], -(x["year"] or 0)))

    # Display summary by score
    print("  ── Heuristic scoring (no API) ──\n")
    for sc in [5, 4, 3, 2, 1]:
        count = len([x for x in scored if x["score"] == sc])
        bar = "█" * sc + "░" * (5 - sc)
        print(f"  {bar}  {count:>2} posts")
    print()

    # Interactive review
    selected = []
    for i, item in enumerate(scored, 1):
        score  = item["score"]
        title  = item["title"]
        year   = item["year"]
        excerpt = item["excerpt"][:60] if item["excerpt"] else "(no excerpt)"

        # Show summary
        bar = "█" * score + "░" * (5 - score)
        print(f"  [{i:3d}/{len(scored)}] {bar}  [{year}]  {title[:50]}")
        print(f"           Excerpt: {excerpt}")
        print()

        # Prompt
        while True:
            try:
                choice = input("  [i]nclude / [s]kip / [q]uit?: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "q"

            if choice == "i":
                selected.append(item["post"])
                print(f"  ✓ Added\n")
                break
            elif choice == "s" or choice == "":
                print()
                break
            elif choice == "q":
                print(f"\n  Stopping.\n")
                break
            else:
                print(f"  Invalid: {choice}")

        if choice == "q":
            break

    if selected:
        # Build output JSON
        result_posts = []
        for post in selected:
            year = int((post.get("published_at") or "")[:4]) if post.get("published_at") else 2020
            slug = post["slug"]
            url  = f"https://{BLOG_DOMAIN}/{slug}/"

            entry = {
                "tipo": "Blog",
                "anio": year,
                "rol": "Actor(a)",
                "titulo": post["title"],
                "enlace": url,
                "dirigidoA": "Público adulto",
                "descripcion": post.get("custom_excerpt", "")[:200],  # placeholder
                "slug": slug,
                "published_at": post.get("published_at"),
                "_review_status": "pending",
                "_review_notes": "",
                "_meta": {
                    "_status": "pending",
                    "_rizoma_id": None,
                    "_uploaded_at": None,
                    "_notes": "",
                },
            }
            result_posts.append(entry)

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_evaluated": len(scored),
            "selected_count": len(selected),
            "posts": result_posts,
        }

        OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"  ═══════════════════════════════════════")
        print(f"  ✓ Selected {len(selected)}/{len(scored)} posts")
        print(f"  ✓ Saved → {OUTPUT_FILE}")
        print(f"\n  Next: python3 scripts/07_review_blog.py\n")
    else:
        print("  (No posts selected)")


if __name__ == "__main__":
    run()
