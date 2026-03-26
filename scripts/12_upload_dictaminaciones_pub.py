"""
rizoma-automation / 12_upload_dictaminaciones_pub.py
=====================================================
Uploads dictaminaciones-publicaciones records to rizoma.conahcyt.mx /
msaportaciones dictaminaciones-publicaciones.

Reads:   evidence/aportaciones/dictaminaciones-publicaciones/dictaminaciones.json
Writes:  logs/upload_dictaminaciones_pub_log.json
         (also updates _meta in the evidence file)

Usage:
  python3 scripts/12_upload_dictaminaciones_pub.py              # dry-run (default, safe)
  python3 scripts/12_upload_dictaminaciones_pub.py --live        # actually POST
  python3 scripts/12_upload_dictaminaciones_pub.py --live --limit 1   # test with 1 record

Catalog IDs confirmed from dictaminaciones-especializadas existing records:
  rol   → DICTAMINADOR / REVISOR
  tipo  → DICTAMEN_TECNICO / DICTAMEN_ACADEMICO
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
INPUT_FILE = ROOT / "evidence" / "aportaciones" / "dictaminaciones-publicaciones" / "dictaminaciones.json"
LOG_FILE   = ROOT / "logs" / "upload_dictaminaciones_pub_log.json"

BASE = "https://rizoma.conahcyt.mx"
MSAP = f"{BASE}/services/msaportaciones/api"

DRY_RUN = "--live" not in sys.argv
LIMIT   = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

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

# ── Catalog maps ───────────────────────────────────────────────────────────
ROL_MAP = {
    "Dictaminador(a)": {"id": "DICTAMINADOR", "nombre": "Dictaminador(a)"},
    "Revisor(a)":      {"id": "REVISOR",       "nombre": "Revisor(a)"},
}

TIPO_MAP = {
    "Dictamen técnico":   {"id": "DICTAMEN_TECNICO",   "nombre": "Dictamen técnico"},
    "Dictamen académico": {"id": "DICTAMEN_ACADEMICO", "nombre": "Dictamen académico"},
}


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
            raw = r.read().decode(errors="replace").strip()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace").strip()
        return e.code, {"error": raw[:600]}


# ── Payload ────────────────────────────────────────────────────────────────────

def build_payload(item):
    rol_text  = item.get("rol", "Dictaminador(a)")
    tipo_text = item.get("tipo", "Dictamen académico")
    rol_obj   = ROL_MAP.get(rol_text)
    tipo_obj  = TIPO_MAP.get(tipo_text)

    if not rol_obj:
        raise ValueError(f"Unknown rol: {rol_text!r}. Valid: {list(ROL_MAP)}")
    if not tipo_obj:
        raise ValueError(f"Unknown tipo: {tipo_text!r}. Valid: {list(TIPO_MAP)}")

    return {
        "anio":        str(item["anio"]),
        "rol":         rol_obj,
        "titulo":      item["titulo"],
        "tipo":        tipo_obj,
        "descripcion": item["descripcion"],
        "productoPrincipal": False,
    }


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_one(item, hdrs):
    log = {
        "titulo":    item["titulo"],
        "anio":      item["anio"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run":   DRY_RUN,
        "status":    None,
        "rizoma_id": None,
        "error":     None,
    }

    try:
        payload = build_payload(item)
    except ValueError as e:
        log["status"] = "error"
        log["error"]  = str(e)
        return log

    if DRY_RUN:
        log["status"] = "dry_run"
        log["payload_preview"] = payload
        return log

    status, resp = post_json(f"{MSAP}/dictaminaciones-publicaciones", payload, hdrs)
    log["status"] = status
    if status in (200, 201):
        rizoma_id = resp.get("id")
        if not rizoma_id:
            try:
                records = get_json(f"{MSAP}/dictaminaciones-publicaciones?page=1&size=50", hdrs)
                match = next(
                    (r for r in records
                     if r.get("titulo") == item["titulo"] and str(r.get("anio")) == str(item["anio"])),
                    None
                )
                rizoma_id = match["id"] if match else None
            except Exception:
                pass
        log["rizoma_id"] = rizoma_id
        item.setdefault("_meta", {})
        item["_meta"]["_status"]      = "uploaded_meta"
        item["_meta"]["_rizoma_id"]   = rizoma_id
        item["_meta"]["_uploaded_at"] = log["timestamp"]
    else:
        log["error"] = str(resp)[:400]
        item.setdefault("_meta", {})
        item["_meta"]["_notes"] = f"HTTP {status}: {log['error'][:200]}"

    return log


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Dictaminaciones Publicaciones Uploader              ║")
    print(f"║  {'DRY RUN — pass --live to upload':52s}║" if DRY_RUN else
          f"║  {'LIVE MODE — WRITING TO PLATFORM':52s}║")
    print("╚══════════════════════════════════════════════════════╝\n")

    if not INPUT_FILE.exists():
        print(f"  ✗ Input file not found: {INPUT_FILE}")
        sys.exit(1)

    data  = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    items = data.get("posts", data.get("items", []))

    # Skip already uploaded / already_exists
    queue = [it for it in items
             if it.get("_meta", {}).get("_status", "pending") == "pending"]

    print(f"  Records in file : {len(items)}")
    print(f"  To upload       : {len(queue)}")
    if LIMIT:
        queue = queue[:LIMIT]
        print(f"  --limit {LIMIT}       : processing {len(queue)}")
    print()

    if not queue:
        print("  Nothing to upload.")
        return

    hdrs = get_headers()

    logs    = []
    success = 0
    failed  = 0

    for i, item in enumerate(queue, 1):
        title = item.get("titulo", "")[:60]
        print(f"  [{i}/{len(queue)}] {title}")

        log = upload_one(item, hdrs)
        logs.append(log)

        if DRY_RUN:
            p = log.get("payload_preview", {})
            if p:
                print(f"    anio       = {p['anio']}")
                print(f"    rol        = {p['rol']}")
                print(f"    tipo       = {p['tipo']}")
                print(f"    titulo     = {p['titulo'][:70]}")
                print(f"    descripcion= {len(p['descripcion'])} chars")
            else:
                print(f"    ✗ SKIPPED — {log.get('error','')}")
        elif log["status"] in (200, 201):
            print(f"    ✓ uploaded — rizoma_id = {log['rizoma_id']}")
            success += 1
            time.sleep(0.4)
        else:
            print(f"    ✗ FAILED — HTTP {log['status']}: {log.get('error','')[:100]}")
            failed += 1
            time.sleep(0.4)
        print()

    # Persist updated _meta
    if not DRY_RUN:
        INPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Append to log
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
    print(f"  Log → logs/upload_dictaminaciones_pub_log.json\n")


if __name__ == "__main__":
    run()
