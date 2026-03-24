"""
rizoma-automation / 07_review_blog.py
======================================
Interactive terminal tool to review the AI-evaluated blog posts and decide
which ones to include in Rizoma as "medios escritos > Blog".

Reads:   raw_evidence/divulgacion_blog_evaluated.json
Writes:  raw_evidence/divulgacion_blog_evaluated.json  (updates in place)
Exports: evidence/acceso-universal/medios-escritos/blog_divulgacion.json
         (only accepted posts, ready for upload)

Usage:
  python3 scripts/07_review_blog.py               # review all posts
  python3 scripts/07_review_blog.py --pending      # only unreviewed posts
  python3 scripts/07_review_blog.py --review       # only AI-flagged "review"
  python3 scripts/07_review_blog.py --stats        # show summary and exit

Controls (per post):
  a  →  accept (include in upload)
  r  →  reject (exclude)
  e  →  edit description (opens inline editor)
  s  →  skip (decide later)
  o  →  open URL in browser
  q  →  quit and save
"""

import json
import os
import sys
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime, timezone

ROOT        = Path(__file__).parent.parent
RAW_DIR     = ROOT / "raw_evidence"
INPUT_FILE  = RAW_DIR / "divulgacion_blog_filtered.json"
EXPORT_FILE = ROOT / "evidence" / "acceso-universal" / "medios-escritos" / "blog_divulgacion.json"

SHOW_PENDING = "--pending" in sys.argv
SHOW_REVIEW  = "--review"  in sys.argv
STATS_ONLY   = "--stats"   in sys.argv

# ── Terminal helpers ──────────────────────────────────────────────────────────

def clear():
    os.system("clear")

def wrap(text: str, width: int = 72, indent: str = "") -> str:
    return textwrap.fill(str(text), width=width, initial_indent=indent,
                         subsequent_indent=indent)

def bar(score: int) -> str:
    filled = "█" * score
    empty  = "░" * (5 - score)
    return f"{filled}{empty} {score}/5"

def status_color(status: str) -> str:
    return {"accepted": "✓", "rejected": "✗", "include": "●", "review": "?", "exclude": "○"}.get(status, "·")

def prompt_line(post: dict, i: int, total: int) -> str:
    rec   = post.get("_ai_recommendation", "?")
    rev   = post.get("_review_status", "pending")
    score = post.get("_ai_score", 0)
    icon  = status_color(rev)
    return f"[{i}/{total}] {icon} score={score} ai={rec}  {post['titulo'][:55]}"

# ── Display ───────────────────────────────────────────────────────────────────

def show_post(post: dict, idx: int, total: int):
    clear()
    score = post.get("_ai_score", 0)
    rec   = post.get("_ai_recommendation", "—")
    rev   = post.get("_review_status", "pending")

    print("━" * 72)
    print(f"  POST {idx}/{total}   AI: {bar(score)}   Recommendation: {rec.upper()}   Status: {rev.upper()}")
    print("━" * 72)
    print()
    print(wrap(post["titulo"], indent="  TÍTULO:  "))
    print(f"  URL:     {post['enlace']}")
    print(f"  Año:     {post['anio']}    Tipo: {post['tipo']}    Rol: {post['rol']}")
    print(f"  Público: {post.get('dirigidoA', '—')}")
    print()
    print("  ── AI Reasoning " + "─" * 55)
    print(wrap(post.get("_ai_reasoning", "—"), indent="  "))
    print()
    print("  ── Descripción propuesta " + "─" * 46)
    desc = post.get("descripcion", "")
    print(wrap(desc, indent="  "))
    print(f"  ({len(desc)} caracteres)")
    print()
    print("─" * 72)
    print("  [a] Aceptar   [r] Rechazar   [e] Editar descripción")
    print("  [s] Saltar    [o] Abrir URL  [q] Guardar y salir")
    print("─" * 72)

# ── Description editor ────────────────────────────────────────────────────────

def edit_description(post: dict) -> str:
    """Inline multi-line description editor."""
    clear()
    print("━" * 72)
    print(f"  EDITAR DESCRIPCIÓN — {post['titulo'][:50]}")
    print("  Target: 400–500 caracteres. Escribe el texto y termina con una línea vacía.")
    print("━" * 72)
    print(f"\n  Actual ({len(post.get('descripcion',''))} chars):")
    print(wrap(post.get("descripcion", ""), indent="  "))
    print("\n  Nueva descripción (Enter en línea vacía para terminar, Ctrl+C para cancelar):")

    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelado.")
        return post.get("descripcion", "")

    new_desc = " ".join(lines).strip()
    if not new_desc:
        return post.get("descripcion", "")

    print(f"\n  Nueva descripción ({len(new_desc)} chars):")
    print(wrap(new_desc, indent="  "))
    confirm = input("\n  ¿Guardar? [s/n]: ").strip().lower()
    return new_desc if confirm == "s" else post.get("descripcion", "")

# ── Stats ─────────────────────────────────────────────────────────────────────

def show_stats(posts: list):
    accepted = [p for p in posts if p.get("_review_status") == "accepted"]
    rejected = [p for p in posts if p.get("_review_status") == "rejected"]
    pending  = [p for p in posts if p.get("_review_status") not in ("accepted", "rejected")]
    ai_inc   = [p for p in posts if p.get("_ai_recommendation") == "include"]
    ai_rev   = [p for p in posts if p.get("_ai_recommendation") == "review"]
    ai_exc   = [p for p in posts if p.get("_ai_recommendation") == "exclude"]

    print("\n  ══════════════════ RESUMEN ══════════════════")
    print(f"  Total evaluados:    {len(posts):>3}")
    print(f"  ✓ Aceptados:        {len(accepted):>3}")
    print(f"  ✗ Rechazados:       {len(rejected):>3}")
    print(f"  · Sin revisar:      {len(pending):>3}")
    print()
    print(f"  AI → include:       {len(ai_inc):>3}")
    print(f"  AI → review:        {len(ai_rev):>3}")
    print(f"  AI → exclude:       {len(ai_exc):>3}")
    print()
    by_year = {}
    for p in accepted:
        y = p.get("anio", "?")
        by_year[y] = by_year.get(y, 0) + 1
    if by_year:
        print("  Aceptados por año:")
        for y in sorted(by_year):
            print(f"    {y}: {by_year[y]}")

# ── Save ──────────────────────────────────────────────────────────────────────

def save_all(data: dict, posts: list):
    accepted = [p for p in posts if p.get("_review_status") == "accepted"]
    data["posts"] = posts
    data["accepted_count"]  = len(accepted)
    data["rejected_count"]  = len([p for p in posts if p.get("_review_status") == "rejected"])
    data["pending_count"]   = len([p for p in posts if p.get("_review_status") not in ("accepted","rejected")])
    data["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    INPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Export accepted posts (upload-ready)
    EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    upload_ready = []
    for p in accepted:
        entry = {
            "tipo":        p["tipo"],
            "anio":        p["anio"],
            "rol":         p["rol"],
            "titulo":      p["titulo"],
            "enlace":      p["enlace"],
            "dirigidoA":   p.get("dirigidoA", "Público adulto"),
            "descripcion": p.get("descripcion", ""),
            "_meta": p.get("_meta", {
                "_status": "pending",
                "_rizoma_id": None,
                "_uploaded_at": None,
                "_notes": "",
            }),
        }
        upload_ready.append(entry)

    export = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "section": "medios-escritos",
        "tipo": "Blog",
        "count": len(upload_ready),
        "items": upload_ready,
    }
    EXPORT_FILE.write_text(json.dumps(export, indent=2, ensure_ascii=False))
    print(f"\n  ✓ Saved {len(posts)} posts → {INPUT_FILE.name}")
    print(f"  ✓ Exported {len(upload_ready)} accepted → evidence/acceso-universal/medios-escritos/blog_divulgacion.json")

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not INPUT_FILE.exists():
        print(f"  ✗ {INPUT_FILE} not found.")
        print("    Run scripts/06_filter_blog.py first.")
        sys.exit(1)

    data  = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    posts = data.get("posts", [])

    if STATS_ONLY:
        show_stats(posts)
        print()
        return

    # Filter which posts to show
    if SHOW_PENDING:
        queue = [p for p in posts if p.get("_review_status") not in ("accepted","rejected")]
        print(f"  Showing {len(queue)} unreviewed posts")
    elif SHOW_REVIEW:
        queue = [p for p in posts if p.get("_ai_recommendation") == "review"]
        print(f"  Showing {len(queue)} AI-flagged 'review' posts")
    else:
        # Default: show AI-recommended includes + reviews first, then rest
        queue = sorted(posts, key=lambda p: (
            {"include": 0, "review": 1, "exclude": 2}.get(p.get("_ai_recommendation","review"), 1),
            -p.get("_ai_score", 0),
        ))

    total = len(queue)
    i = 0

    while i < total:
        post = queue[i]
        # Find this post's index in the master list
        master_idx = next((j for j, p in enumerate(posts) if p["slug"] == post["slug"]), None)

        show_post(post, i + 1, total)

        try:
            cmd = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            cmd = "q"

        if cmd == "a":
            post["_review_status"] = "accepted"
            if master_idx is not None:
                posts[master_idx] = post
            print(f"  ✓ Aceptado")
            i += 1
        elif cmd == "r":
            post["_review_status"] = "rejected"
            if master_idx is not None:
                posts[master_idx] = post
            print(f"  ✗ Rechazado")
            i += 1
        elif cmd == "e":
            new_desc = edit_description(post)
            post["descripcion"] = new_desc
            if master_idx is not None:
                posts[master_idx] = post
            # Stay on same post to confirm
        elif cmd == "s":
            i += 1
        elif cmd == "o":
            url = post.get("enlace", "")
            if url:
                subprocess.run(["open", url], check=False)
        elif cmd == "q":
            break
        elif cmd in ("n", ""):
            i += 1
        elif cmd == "p" and i > 0:
            i -= 1
        else:
            print(f"  Comando no reconocido: '{cmd}'")

    save_all(data, posts)
    show_stats(posts)
    print()


if __name__ == "__main__":
    run()
