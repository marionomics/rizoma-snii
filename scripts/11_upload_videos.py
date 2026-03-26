"""
rizoma-automation / 11_upload_videos.py
========================================
Uploads audiovisual records to rizoma.conahcyt.mx /
msaportaciones audiovisuales-radiofonicos-digitales.

Reads:   evidence/acceso-universal/audiovisuales-radiofonicos-digitales/videos_youtube.json
Writes:  logs/upload_videos_log.json
         (also updates _meta in the evidence file)

Usage:
  python3 scripts/11_upload_videos.py              # dry-run (default, safe)
  python3 scripts/11_upload_videos.py --live        # actually POST
  python3 scripts/11_upload_videos.py --live --limit 1   # test with 1 record

Catalog IDs confirmed from existing records:
  audiovisualesRadiofonicosDigitales → CAPSULAS_VIDEO
  rol                                → ACTOR / PARTICIPANTE
  dirigidoA options                  → same as medios-escritos (1–11)
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
INPUT_FILE = ROOT / "evidence" / "acceso-universal" / "audiovisuales-radiofonicos-digitales" / "videos_youtube.json"
LOG_FILE   = ROOT / "logs" / "upload_videos_log.json"

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
TIPO_VIDEO = {"id": "CAPSULAS_VIDEO", "nombre": "Cápsulas de video (Reels, Facebook, TikTok o YouTube)"}

ROL_MAP = {
    "Actor(a)":    {"id": "ACTOR",       "nombre": "Actor(a)"},
    "Participante":{"id": "PARTICIPANTE","nombre": "Participante"},
}

DIRIGIDO_MAP = {
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

def build_payload(video):
    rol_text     = video.get("rol", "Actor(a)")
    dirigido_text = video.get("dirigidoA", "Sector estudiantil")
    return {
        "anio":                          str(video["anio"]),
        "titulo":                        video["titulo"],
        "enlace":                        video.get("enlace", ""),
        "descripcion":                   video["descripcion"],
        "audiovisualesRadiofonicosDigitales": TIPO_VIDEO,
        "rol":                           ROL_MAP.get(rol_text, ROL_MAP["Actor(a)"]),
        "dirigidoA":                     DIRIGIDO_MAP.get(dirigido_text, DIRIGIDO_MAP["Sector estudiantil"]),
        "institucion":                   INSTITUCION,
        "productoPrincipal":             False,
    }


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_one(video, hdrs):
    payload = build_payload(video)
    log = {
        "titulo":    video["titulo"],
        "anio":      video["anio"],
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

    status, resp = post_json(f"{MSAP}/audiovisuales-radiofonicos-digitales", payload, hdrs)
    log["status"] = status
    if status in (200, 201):
        rizoma_id = resp.get("id")
        if not rizoma_id:
            try:
                records = get_json(f"{MSAP}/audiovisuales-radiofonicos-digitales?page=1&size=50", hdrs)
                match = next(
                    (r for r in records
                     if r.get("titulo") == video["titulo"] and str(r.get("anio")) == str(video["anio"])),
                    None
                )
                rizoma_id = match["id"] if match else None
            except Exception:
                pass
        log["rizoma_id"] = rizoma_id
        video.setdefault("_meta", {})
        video["_meta"]["_status"]      = "uploaded_meta"
        video["_meta"]["_rizoma_id"]   = rizoma_id
        video["_meta"]["_uploaded_at"] = log["timestamp"]
    else:
        log["error"] = str(resp)[:400]
        video.setdefault("_meta", {})
        video["_meta"]["_notes"] = f"HTTP {status}: {log['error'][:200]}"

    return log


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Video Uploader — audiovisuales-radiofonicos-digitales║")
    print(f"║  {'DRY RUN — pass --live to upload':52s}║" if DRY_RUN else
          f"║  {'LIVE MODE — WRITING TO PLATFORM':52s}║")
    print("╚══════════════════════════════════════════════════════╝\n")

    if not INPUT_FILE.exists():
        print(f"  ✗ Input file not found: {INPUT_FILE}")
        sys.exit(1)

    data   = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    videos = data.get("posts", data.get("items", []))

    # Skip already uploaded / already_exists
    queue = [v for v in videos
             if v.get("_meta", {}).get("_status", "pending") == "pending"]

    print(f"  Videos in file : {len(videos)}")
    print(f"  To upload      : {len(queue)}")
    if LIMIT:
        queue = queue[:LIMIT]
        print(f"  --limit {LIMIT}      : processing {len(queue)}")
    print()

    if not queue:
        print("  Nothing to upload.")
        return

    # Validate descriptions
    short = [v for v in queue if len(v.get("descripcion", "")) < 500]
    if short:
        print(f"  ⚠ {len(short)} video(s) have descriptions under 500 chars — will be rejected by platform:")
        for v in short:
            print(f"    · {v['titulo'][:60]} ({len(v.get('descripcion',''))} chars)")
        print()

    hdrs = get_headers()

    logs    = []
    success = 0
    failed  = 0

    for i, video in enumerate(queue, 1):
        title = video.get("titulo", "")[:60]
        print(f"  [{i}/{len(queue)}] {title}")

        log = upload_one(video, hdrs)
        logs.append(log)

        if DRY_RUN:
            p = log["payload_preview"]
            print(f"    anio            = {p['anio']}")
            print(f"    audiovisuales   = {p['audiovisualesRadiofonicosDigitales']}")
            print(f"    rol             = {p['rol']}")
            print(f"    dirigidoA       = {p['dirigidoA']}")
            print(f"    institucion     = id={p['institucion']['id']} {p['institucion']['nombre']}")
            print(f"    descripcion     = {len(p['descripcion'])} chars")
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
    print(f"  Log → logs/upload_videos_log.json\n")


if __name__ == "__main__":
    run()
