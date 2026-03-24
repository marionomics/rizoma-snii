"""
rizoma-automation / 10_upload_blog.py
======================================
Uploads blog posts to rizoma.conahcyt.mx / msaportaciones medios-escritos.

Usage:
  python3 scripts/10_upload_blog.py              # dry-run (default, safe)
  python3 scripts/10_upload_blog.py --live        # actually POST
  python3 scripts/10_upload_blog.py --live --limit 1   # test with 1 post

Catalog IDs confirmed from existing record on 2026-03-24:
  mediosEscritos  → BLOG / Blog
  rol             → ACTOR / Actor(a)
  dirigidoA       → 1 / Público adulto
  institucion     → read from .env (INSTITUCION_ID, INSTITUCION_CLAVE, etc.)
"""

import json
import sys
import ssl
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from auth import get_headers, load_env

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "evidence" / "acceso-universal" / "medios-escritos" / "blog_divulgacion.json"
LOG_FILE   = ROOT / "logs" / "upload_blog_log.json"

BASE = "https://rizoma.conahcyt.mx"
MSAP = f"{BASE}/services/msaportaciones/api"

DRY_RUN = "--live" not in sys.argv
LIMIT   = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

# SSL workaround for government cert
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE

# ── Load institution from .env ──────────────────────────────────────────────
_env = load_env()

def _require(key):
    v = _env.get(key, "").strip()
    if not v:
        print(f"  ✗ {key} not set in .env")
        sys.exit(1)
    return v

INSTITUCION = {
    "id":       int(_require("INSTITUCION_ID")),
    "clave":    _require("INSTITUCION_CLAVE"),
    "nombre":   _require("INSTITUCION_NOMBRE"),
    "tipo":     {"id": "01", "nombre": "Nacional"},
    "pais":     {"id": "MEX", "nombre": "México"},
    "entidad":  {"clave": _require("INSTITUCION_ESTADO_CLAVE"),
                 "nombre": _require("INSTITUCION_ESTADO_NOMBRE")},
    "nivelUno": {"id": _require("INSTITUCION_NIVEL_UNO_ID"),
                 "nombre": _require("INSTITUCION_NIVEL_UNO_NOMBRE")},
    "nivelDos": {"id": _require("INSTITUCION_NIVEL_DOS_ID"),
                 "nombre": _require("INSTITUCION_NIVEL_DOS_NOMBRE")},
}

# ── Fixed catalog objects ───────────────────────────────────────────────────
TIPO_BLOG = {"id": "BLOG", "nombre": "Blog"}
ROL_ACTOR = {"id": "ACTOR", "nombre": "Actor(a)"}
DIRIGIDO_PUBLICO_ADULTO = {"id": "1", "nombre": "Público adulto"}



# ── HTTP ───────────────────────────────────────────────────────────────────────

def get_json(url, hdrs):
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, context=_CTX, timeout=15) as r:
        return json.loads(r.read().decode())

def post_json(url, payload, hdrs):
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=15) as r:
            body = r.read().decode(errors="replace").strip()
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").strip()
        return e.code, {"error": body[:600]}


# ── Payload ────────────────────────────────────────────────────────────────────

def build_payload(post):
    # Map dirigidoA text → catalog object (default: Público adulto)
    dirigido_map = {
        "Público adulto":     {"id": "1",  "nombre": "Público adulto"},
        "Público en general": {"id": "2",  "nombre": "Público en general"},
        "Público infantil":   {"id": "3",  "nombre": "Público infantil"},
        "Público juvenil":    {"id": "4",  "nombre": "Público juvenil"},
        "Sector empresarial": {"id": "5",  "nombre": "Sector empresarial"},
        "Sector estudiantil": {"id": "6",  "nombre": "Sector estudiantil"},
        "Sector gobierno":    {"id": "7",  "nombre": "Sector gobierno"},
        "Sector industrial":  {"id": "8",  "nombre": "Sector industrial"},
        "Sector judicial":    {"id": "9",  "nombre": "Sector judicial"},
        "Sector legislativo": {"id": "10", "nombre": "Sector legislativo"},
        "Otro":               {"id": "11", "nombre": "Otro"},
    }
    dirigido_text = post.get("dirigidoA", "Público adulto")
    dirigido_obj  = dirigido_map.get(dirigido_text, DIRIGIDO_PUBLICO_ADULTO)

    return {
        "anio":            str(post["anio"]),
        "titulo":          post["titulo"],
        "enlace":          post.get("enlace", ""),
        "descripcion":     post["descripcion"],
        "mediosEscritos":  TIPO_BLOG,
        "rol":             ROL_ACTOR,
        "dirigidoA":       dirigido_obj,
        "institucion":     INSTITUCION,
        "productoPrincipal": False,
    }


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_one(post, hdrs):
    payload = build_payload(post)
    log = {
        "titulo":    post["titulo"],
        "anio":      post["anio"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run":   DRY_RUN,
        "status":    None,
        "rizoma_id": None,
        "error":     None,
    }

    if DRY_RUN:
        log["status"] = "dry_run"
        log["payload_preview"] = payload
        return log

    status, resp = post_json(f"{MSAP}/medios-escritos", payload, hdrs)
    log["status"] = status
    if status in (200, 201):
        # Server returns empty body — fetch the list and match by titulo+anio to get ID
        rizoma_id = resp.get("id")
        if not rizoma_id:
            try:
                records = get_json(f"{MSAP}/medios-escritos?page=1&size=50", hdrs)
                match = next(
                    (r for r in records
                     if r.get("titulo") == post["titulo"] and str(r.get("anio")) == str(post["anio"])),
                    None
                )
                rizoma_id = match["id"] if match else None
            except Exception:
                pass
        log["rizoma_id"] = rizoma_id
        post.setdefault("_meta", {})
        post["_meta"]["_status"]      = "uploaded_meta"
        post["_meta"]["_rizoma_id"]   = rizoma_id
        post["_meta"]["_uploaded_at"] = log["timestamp"]
    else:
        log["error"] = str(resp)[:400]
        post.setdefault("_meta", {})
        post["_meta"]["_notes"] = f"HTTP {status}: {log['error'][:200]}"

    return log


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Blog Uploader — medios-escritos                     ║")
    print(f"║  {'DRY RUN — pass --live to upload':52s}║" if DRY_RUN else
          f"║  {'LIVE MODE — WRITING TO PLATFORM':52s}║")
    print("╚══════════════════════════════════════════════════════╝\n")

    data  = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    posts = data.get("posts", data.get("items", []))

    # Build queue: skip already uploaded
    queue = [p for p in posts
             if p.get("_meta", {}).get("_status", "pending") == "pending"]
    if not any("_meta" in p for p in posts):
        queue = posts  # no _meta fields yet → upload everything

    print(f"  Posts in file : {len(posts)}")
    print(f"  To upload     : {len(queue)}")
    if LIMIT:
        queue = queue[:LIMIT]
        print(f"  --limit {LIMIT}     : processing {len(queue)}")
    print()

    if not queue:
        print("  Nothing to upload.")
        return

    hdrs = get_headers()

    logs    = []
    success = 0
    failed  = 0

    for i, post in enumerate(queue, 1):
        title = post.get("titulo", "")[:60]
        print(f"  [{i}/{len(queue)}] {title}")

        log = upload_one(post, hdrs)
        logs.append(log)

        if DRY_RUN:
            p = log["payload_preview"]
            print(f"    anio          = {p['anio']}")
            print(f"    mediosEscritos= {p['mediosEscritos']}")
            print(f"    rol           = {p['rol']}")
            print(f"    dirigidoA     = {p['dirigidoA']}")
            print(f"    institucion   = id={p['institucion']['id']} {p['institucion']['nombre']}")
            print(f"    descripcion   = {len(p['descripcion'])} chars")
        elif log["status"] in (200, 201):
            print(f"    ✓ uploaded — rizoma_id = {log['rizoma_id']}")
            success += 1
            time.sleep(0.4)
        else:
            print(f"    ✗ FAILED — HTTP {log['status']}: {log.get('error','')[:100]}")
            failed += 1
            time.sleep(0.4)
        print()

    # Persist updated _meta back to file
    if not DRY_RUN:
        INPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Append to log file
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(LOG_FILE.read_text()).get("entries", []) if LOG_FILE.exists() else []
    LOG_FILE.write_text(json.dumps({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "entries":  prev + logs,
    }, indent=2, ensure_ascii=False))

    print("  ══════════════════════════════════════════════════════")
    if DRY_RUN:
        print(f"  Dry run complete — {len(logs)} items previewed")
        print(f"  Run with --live --limit 1 to test a real upload")
    else:
        print(f"  ✓ Uploaded : {success}")
        print(f"  ✗ Failed   : {failed}")
    print(f"  Log → logs/upload_blog_log.json\n")


if __name__ == "__main__":
    run()
