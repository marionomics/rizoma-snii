"""
rizoma-automation / 13_upload_docs_dictaminaciones_pub.py
==========================================================
Uploads PDF evidence documents for dictaminaciones-publicaciones records.

For each record in the JSON that has _status="uploaded_meta" and a _notion_id:
  1. Downloads the PDF from Notion (via the Archivo property)
  2. Base64-encodes it and POSTs to dmsms (document storage service)
  3. Gets the tlapiakali URI from the 201 Location header
  4. PUTs the full record + documento field to msaportaciones
  5. Updates _status to "complete" in the JSON

Usage:
  python3 scripts/13_upload_docs_dictaminaciones_pub.py              # dry-run
  python3 scripts/13_upload_docs_dictaminaciones_pub.py --live        # upload
  python3 scripts/13_upload_docs_dictaminaciones_pub.py --live --limit 1

Upload flow (reverse-engineered 2026-03-26):
  POST /services/dmsms/api/documentos/RIZOMA/convocatorias/perfil/{CVU}?etapa=REGISTRO
       body: {"nombre": "file.pdf", "contenido": "<base64>"}
       response: 201, Location header = tlapiakali URI

  PUT  /services/msaportaciones/api/dictaminaciones-publicaciones/{id}
       body: full record + "documento": {"nombre", "contentType", "uri", "definicionDocumento": "1", "size"}
"""

import json
import sys
import ssl
import time
import base64
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from auth import get_headers, load_env

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "evidence" / "aportaciones" / "dictaminaciones-publicaciones" / "dictaminaciones.json"
LOG_FILE   = ROOT / "logs" / "upload_docs_dictaminaciones_pub_log.json"

BASE  = "https://rizoma.conahcyt.mx"
MSAP  = f"{BASE}/services/msaportaciones/api"
DMSMS = f"{BASE}/services/dmsms/api"

DRY_RUN = "--live" not in sys.argv
LIMIT   = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE

_env = load_env()
CVU  = _env.get("RIZOMA_CVU", "").strip()
NOTION_TOKEN = _env.get("NOTION_TOKEN", "").strip()

ROL_MAP  = {
    "Dictaminador(a)": {"id": "DICTAMINADOR",  "nombre": "Dictaminador(a)"},
    "Revisor(a)":      {"id": "REVISOR",        "nombre": "Revisor(a)"},
}
TIPO_MAP = {
    "Dictamen técnico":   {"id": "DICTAMEN_TECNICO",  "nombre": "Dictamen técnico"},
    "Dictamen académico": {"id": "DICTAMEN_ACADEMICO","nombre": "Dictamen académico"},
}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def api_get(url, hdrs):
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, context=_CTX, timeout=20) as r:
        return json.loads(r.read().decode())

def api_post_json(url, payload, hdrs):
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=30) as r:
            location = r.headers.get("Location", "")
            raw = r.read().decode(errors="replace").strip()
            return r.status, location, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace").strip()
        return e.code, "", {"error": raw[:600]}

def api_put_json(url, payload, hdrs, retries=3):
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers=hdrs, method="PUT")
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=45) as r:
                raw = r.read().decode(errors="replace").strip()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace").strip()
            return e.code, {"error": raw[:600]}
        except (ConnectionResetError, OSError, TimeoutError) as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"    (network error, retry {attempt+1}/{retries-1} in {wait}s: {e})")
                time.sleep(wait)
            else:
                return 0, {"error": f"Network error after {retries} attempts: {e}"}


# ── Notion PDF fetcher ─────────────────────────────────────────────────────────

def fetch_notion_pdf(notion_id: str, pdf_filename: str) -> bytes | None:
    """
    Download PDF bytes from a Notion page's Archivo file property.
    If the page has multiple files, selects by matching the _pdf filename suffix (_0, _1...).
    """
    n_hdrs = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
    }
    # Get page
    req  = urllib.request.Request(f"https://api.notion.com/v1/pages/{notion_id}", headers=n_hdrs)
    with urllib.request.urlopen(req, context=_CTX, timeout=25) as r:
        page = json.loads(r.read().decode())

    # Find Archivo property (files)
    all_files = []
    for prop_name, prop_val in page.get("properties", {}).items():
        if prop_val.get("type") == "files":
            for f in prop_val.get("files", []):
                if f.get("type") == "file":
                    all_files.append(f["file"]["url"])

    if not all_files:
        return None

    # Determine which file index to use from _pdf suffix (_0, _1, ...)
    idx = 0
    import re
    m = re.search(r"_(\d+)\.pdf$", pdf_filename)
    if m:
        idx = int(m.group(1))

    if idx >= len(all_files):
        idx = 0

    url = all_files[idx]
    req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req2, context=_CTX, timeout=30) as r:
        return r.read()


# ── Upload one document ────────────────────────────────────────────────────────

def upload_doc(item, hdrs):
    notion_id  = item.get("_notion_id", "")
    pdf_name   = item.get("_pdf", "")
    rizoma_id  = item.get("_meta", {}).get("_rizoma_id")
    log = {
        "titulo":    item["titulo"],
        "anio":      item["anio"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run":   DRY_RUN,
        "status":    None,
        "error":     None,
    }

    if not rizoma_id:
        log["status"] = "skip"
        log["error"]  = "No _rizoma_id — metadata not yet uploaded"
        return log

    if not notion_id:
        log["status"] = "skip"
        log["error"]  = "No _notion_id — cannot fetch PDF"
        return log

    # Download PDF
    print(f"    Downloading PDF from Notion ({notion_id[:8]}...)...")
    try:
        pdf_bytes = fetch_notion_pdf(notion_id, pdf_name)
    except Exception as e:
        log["status"] = "error"
        log["error"]  = f"Notion download failed: {e}"
        return log

    if not pdf_bytes:
        log["status"] = "error"
        log["error"]  = "No file found in Notion page"
        return log

    print(f"    PDF: {len(pdf_bytes):,} bytes")
    log["pdf_size"] = len(pdf_bytes)

    if DRY_RUN:
        log["status"] = "dry_run"
        log["dry_info"] = f"Would upload {pdf_name} ({len(pdf_bytes):,} bytes) to rizoma_id={rizoma_id}"
        return log

    # Step 1: upload to dmsms (base64 JSON)
    dmsms_url = f"{DMSMS}/documentos/RIZOMA/convocatorias/perfil/{CVU}?etapa=REGISTRO"
    filename  = pdf_name or f"dictaminacion_{rizoma_id}.pdf"
    payload   = {
        "nombre":    filename,
        "contenido": base64.b64encode(pdf_bytes).decode(),
    }
    status1, location, resp1 = api_post_json(dmsms_url, payload, hdrs)
    if status1 != 201 or not location:
        log["status"] = "error"
        log["error"]  = f"dmsms POST {status1}: location={location!r} resp={str(resp1)[:200]}"
        return log

    uri = location
    print(f"    dmsms ✓ → {uri}")

    # Step 2: PUT the record with documento
    documento = {
        "nombre":             filename,
        "contentType":        "application/pdf",
        "uri":                uri,
        "definicionDocumento": "1",
        "size":               len(pdf_bytes),
    }
    put_payload = {
        "id":          rizoma_id,
        "anio":        str(item["anio"]),
        "rol":         ROL_MAP[item["rol"]],
        "titulo":      item["titulo"],
        "tipo":        TIPO_MAP[item["tipo"]],
        "descripcion": item["descripcion"],
        "productoPrincipal": False,
        "documento":   documento,
    }
    status2, resp2 = api_put_json(f"{MSAP}/dictaminaciones-publicaciones/{rizoma_id}", put_payload, hdrs)
    if status2 in (200, 201):
        log["status"] = "complete"
        item["_meta"]["_status"]      = "complete"
        item["_meta"]["_uploaded_at"] = log["timestamp"]
        item["_meta"]["_notes"]       = f"doc uri: {uri}"
    else:
        log["status"] = "error"
        log["error"]  = f"PUT {status2}: {str(resp2)[:200]}"
        item["_meta"]["_notes"] = f"doc upload failed: HTTP {status2}"

    return log


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    if not CVU:
        print("  ✗ RIZOMA_CVU not set in .env"); sys.exit(1)
    if not NOTION_TOKEN:
        print("  ✗ NOTION_TOKEN not set in .env"); sys.exit(1)

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Document Uploader — dictaminaciones-publicaciones   ║")
    print(f"║  {'DRY RUN — pass --live to upload':52s}║" if DRY_RUN else
          f"║  {'LIVE MODE — WRITING TO PLATFORM':52s}║")
    print("╚══════════════════════════════════════════════════════╝\n")

    if not INPUT_FILE.exists():
        print(f"  ✗ Input not found: {INPUT_FILE}"); sys.exit(1)

    data  = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    items = data.get("posts", [])

    # Queue: records that have metadata uploaded but no document yet
    queue = [it for it in items
             if it.get("_meta", {}).get("_status") in ("uploaded_meta", "complete")
             and it.get("_notion_id")]
    # In live mode, only redo "complete" if the document is a test file (detected by notes)
    # For now: process all that aren't already complete WITH a real doc
    # Simple rule: process if status != complete OR notes contains "test"
    if not DRY_RUN:
        queue = [it for it in queue
                 if it.get("_meta", {}).get("_status") != "complete"
                 or "test" in it.get("_meta", {}).get("_notes", "").lower()]

    print(f"  Records total   : {len(items)}")
    print(f"  To upload docs  : {len(queue)}")
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
        title = item.get("titulo", "")[:55]
        status = item.get("_meta", {}).get("_status")
        print(f"  [{i}/{len(queue)}] {title}  [{status}]")

        log = upload_doc(item, hdrs)
        logs.append(log)

        if DRY_RUN:
            print(f"    → {log.get('dry_info', log.get('error', ''))}")
        elif log["status"] == "complete":
            print(f"    ✓ document uploaded")
            success += 1
            time.sleep(0.5)
        elif log["status"] == "skip":
            print(f"    – skipped: {log['error']}")
        else:
            print(f"    ✗ FAILED: {log.get('error','')[:100]}")
            failed += 1
            time.sleep(0.5)
        print()

    if not DRY_RUN:
        INPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

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
        print(f"  ✓ Complete : {success}")
        print(f"  ✗ Failed   : {failed}")
    print(f"  Log → logs/upload_docs_dictaminaciones_pub_log.json\n")


if __name__ == "__main__":
    run()
