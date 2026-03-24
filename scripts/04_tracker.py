"""
rizoma-automation / 04_tracker.py
===================================
Generates a complete status report across all 36 SNII sections:
  - What's on the platform (live count from API)
  - What's in local evidence/ files (and their _meta._status)
  - What's empty / still needed

Usage:
  python3 scripts/04_tracker.py            # print to terminal
  python3 scripts/04_tracker.py --md       # also write logs/status_report.md
"""

import json
import sys
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from auth import get_headers

ROOT         = Path(__file__).parent.parent
EVIDENCE_DIR = ROOT / "evidence"
SCHEMAS_DIR  = ROOT / "config" / "schemas"
LOG_DIR     = ROOT / "logs"
REPORT_FILE = LOG_DIR / "status_report.md"

WRITE_MD = "--md" in sys.argv

BASE = "https://rizoma.conahcyt.mx"
MSAP = f"{BASE}/services/msaportaciones/api"
PERF = f"{BASE}/services/msperfil/api"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE

# ── All 36 sections: (display_name, api_service, api_slug, evidence_path, extra_params) ─────
SECTIONS = [
    # Producción / Científica-humanística  (articulos/libros/capitulos need tipo=CIENTIFICA)
    ("Artículos",                   "msaportaciones", "articulos",                         "produccion/cientifica-humanistica/articulos",                      "tipo=CIENTIFICA"),
    ("Libros",                      "msaportaciones", "libros",                            "produccion/cientifica-humanistica/libros",                         "tipo=CIENTIFICA"),
    ("Capítulos",                   "msaportaciones", "capitulos",                         "produccion/cientifica-humanistica/capitulos",                      "tipo=CIENTIFICA"),
    ("Reportes",                    "msaportaciones", "reportes",                          "produccion/cientifica-humanistica/reportes",                       ""),
    ("Informes",                    "msaportaciones", "informes",                          "produccion/cientifica-humanistica/informes",                       ""),
    ("Dossier/Número temático",     "msaportaciones", "dossier-o-numero-tematico",         "produccion/cientifica-humanistica/dossier-o-numero-tematico",      ""),
    ("Antologías",                  "msaportaciones", "antologias",                        "produccion/cientifica-humanistica/antologias",                     ""),
    ("Traducciones",                "msaportaciones", "traducciones",                      "produccion/cientifica-humanistica/traducciones",                   ""),
    ("Prólogos/Estudios intro.",    "msaportaciones", "prologos-estudios-introductorios",  "produccion/cientifica-humanistica/prologos-estudios-introductorios",""),
    ("Curadurías",                  "msaportaciones", "curadurias",                        "produccion/cientifica-humanistica/curadurias",                     ""),
    ("Base de datos primarios",     "msaportaciones", "base-datos-primarios",              "produccion/cientifica-humanistica/base-datos-primarios",           ""),
    # Aportaciones
    ("Desarrollos tecnológicos",    "msaportaciones", "desarrollos-tecnologicos-innovaciones", "aportaciones/desarrollos-tecnologicos-innovaciones",          ""),
    ("Propiedades intelectuales",   "msaportaciones", "propiedades-intelectuales",         "aportaciones/propiedades-intelectuales",                           ""),
    ("Transferencias tecnológicas", "msaportaciones", "transferencias-tecnologicas",       "aportaciones/transferencias-tecnologicas",                         ""),
    ("Informes técnicos",           "msaportaciones", "informes-tecnicos",                 "aportaciones/informes-tecnicos",                                   ""),
    ("Proyectos de investigación",  "msaportaciones", "proyectos-investigacion",           "aportaciones/proyectos-investigacion",                             ""),
    ("Planes de estudio",           "msaportaciones", "planes-estudio",                    "aportaciones/planes-estudio",                                      ""),
    ("Colaboraciones interinst.",   "msaportaciones", "colaboraciones-interinstitucionales","aportaciones/colaboraciones-interinstitucionales",                ""),
    ("Coordinaciones",              "msaportaciones", "coordinaciones",                    "aportaciones/coordinaciones",                                      ""),
    ("Jurados",                     "msaportaciones", "jurados",                           "aportaciones/jurados",                                             ""),
    ("Evaluaciones programas",      "msaportaciones", "evaluaciones-programas-proyectos",  "aportaciones/evaluaciones-programas-proyectos",                    ""),
    ("Dictaminaciones publicac.",   "msaportaciones", "dictaminaciones-publicaciones",     "aportaciones/dictaminaciones-publicaciones",                       ""),
    ("Dictaminaciones especializ.", "msaportaciones", "dictaminaciones-especializadas",    "aportaciones/dictaminaciones-especializadas",                      ""),
    # Fortalecimiento
    ("Cursos impartidos",           "msperfil",       "cursos-impartidos",                 "fortalecimiento/docencia/cursos-impartidos",                       ""),
    ("Diplomados impartidos",       "msperfil",       "diplomados",                        "fortalecimiento/docencia/diplomados-impartidos",                   ""),
    ("Capacitaciones",              "msaportaciones", "capacitaciones",                    "fortalecimiento/docencia/capacitaciones",                          ""),
    ("Talleres",                    "msaportaciones", "talleres",                          "fortalecimiento/docencia/talleres",                                ""),
    ("Seminarios",                  "msaportaciones", "seminarios",                        "fortalecimiento/docencia/seminarios",                              ""),
    ("Tutorías",                    "msaportaciones", "tutorias",                          "fortalecimiento/docencia/tutorias",                                ""),
    ("Trabajos de titulación",      "msperfil",       "tesis",                             "fortalecimiento/trabajos-titulacion",                              ""),
    ("Participación editorial",     "msaportaciones", "participacion-editorial",           "fortalecimiento/participacion-editorial",                          ""),
    # Estancias
    ("Estancias de investigación",  "msperfil",       "estancias",                         "estancias/estancias-investigacion",                                ""),
    # Acceso universal
    ("Medios escritos (Blog)",      "msaportaciones", "medios-escritos",                   "acceso-universal/medios-escritos",                                 ""),
    ("Audiovisuales/Radiofónicos",  "msaportaciones", "audiovisuales-radiofonicos-digitales","acceso-universal/audiovisuales-radiofonicos-digitales",          ""),
    ("Museografía",                 "msaportaciones", "museografia-espacios-educacion-no-formal","acceso-universal/museografia-espacios-educacion-no-formal",  ""),
    ("Eventos de comunicación",     "msaportaciones", "eventos-comunicacion",              "acceso-universal/eventos-comunicacion",                            ""),
]


def fetch_platform_count(service, slug, hdrs, extra_params=""):
    """Return count of records on platform for this section, or None on error."""
    base = MSAP if service == "msaportaciones" else PERF
    suffix = f"&{extra_params}" if extra_params else ""
    # JHipster sections vary: some use page=0, some page=1; max size=100
    for page in (0, 1):
        url = f"{base}/{slug}?page={page}&size=100{suffix}"
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, context=_CTX, timeout=8) as r:
                total = r.getheader("X-Total-Count")
                if total is not None:
                    return int(total)
                body = r.read().decode().strip()
                if not body:
                    return 0
                data = json.loads(body)
                if isinstance(data, list):
                    return len(data)
                if isinstance(data, dict):
                    if "totalElements" in data:
                        return data["totalElements"]
                    if "content" in data:
                        return len(data["content"])
                return None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "auth"
            if e.code in (400, 404, 405) and page == 0:
                continue  # try page=1
            return None
        except Exception:
            return None
    return None

# ── Local evidence ─────────────────────────────────────────────────────────────

def scan_local(evidence_path):
    """
    Returns dict:
      total        → total items across all JSON files in folder
      pending      → _meta._status == pending (or no _meta)
      uploaded     → uploaded_meta or complete
      already      → already_exists
      error        → error
      files        → number of JSON files found
    """
    folder = EVIDENCE_DIR / evidence_path
    counts = {"total": 0, "pending": 0, "uploaded": 0, "already": 0, "error": 0, "files": 0}

    if not folder.exists():
        return counts

    json_files = list(folder.glob("*.json"))
    counts["files"] = len(json_files)

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Could be a bulk file with "items" / "posts" array, or a single record
        if "items" in data:
            items = data["items"]
        elif "posts" in data:
            items = data["posts"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]  # single record

        for item in items:
            counts["total"] += 1
            status = item.get("_meta", {}).get("_status", "pending")
            if status in ("uploaded_meta", "complete"):
                counts["uploaded"] += 1
            elif status == "already_exists":
                counts["already"] += 1
            elif status == "error":
                counts["error"] += 1
            else:
                counts["pending"] += 1

    return counts


# ── Report ─────────────────────────────────────────────────────────────────────

def render_report(rows, generated_at):
    lines = []
    lines.append(f"# SNII Evidence Status Report")
    lines.append(f"Generated: {generated_at}")
    lines.append("")

    # Legend
    lines.append("## Legend")
    lines.append("- **Platform** = records currently on rizoma.conahcyt.mx")
    lines.append("- **Local** = items in evidence/ JSON files")
    lines.append("- **Pending** = local items not yet uploaded")
    lines.append("- **Uploaded** = successfully sent to platform")
    lines.append("- **—** = no local files / section not yet worked on")
    lines.append("")

    # Group by section group
    groups = [
        ("Producción / Científica-humanística", rows[:11]),
        ("Aportaciones",                        rows[11:23]),
        ("Fortalecimiento",                     rows[23:31]),
        ("Estancias",                           rows[31:32]),
        ("Acceso universal al conocimiento",    rows[32:]),
    ]

    for group_name, group_rows in groups:
        lines.append(f"## {group_name}")
        lines.append("")
        lines.append(f"| Sección | Platform | Local | Pending | Uploaded | Notes |")
        lines.append(f"|---------|:--------:|:-----:|:-------:|:--------:|-------|")
        for row in group_rows:
            name, platform, local_total, pending, uploaded, notes = row
            plat_str   = str(platform) if platform not in (None, "auth") else ("🔒" if platform == "auth" else "?")
            local_str  = str(local_total) if local_total > 0 else "—"
            pend_str   = str(pending)   if local_total > 0 else "—"
            upload_str = str(uploaded)  if local_total > 0 else "—"
            lines.append(f"| {name} | {plat_str} | {local_str} | {pend_str} | {upload_str} | {notes} |")
        lines.append("")

    # Summary totals
    total_platform = sum(r[1] for r in rows if isinstance(r[1], int))
    total_local    = sum(r[2] for r in rows)
    total_pending  = sum(r[3] for r in rows)
    total_uploaded = sum(r[4] for r in rows)

    lines.append("## Totals")
    lines.append(f"- Platform records : **{total_platform}**")
    lines.append(f"- Local items      : **{total_local}**")
    lines.append(f"- Pending upload   : **{total_pending}**")
    lines.append(f"- Uploaded         : **{total_uploaded}**")
    lines.append("")

    return "\n".join(lines)


def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  SNII Evidence Tracker                               ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    hdrs = get_headers()

    rows   = []
    col_w  = 30

    # Header
    print(f"  {'Section':{col_w}}  {'Platform':>8}  {'Local':>5}  {'Pending':>7}  {'Uploaded':>8}")
    print(f"  {'─'*col_w}  {'─'*8}  {'─'*5}  {'─'*7}  {'─'*8}")

    for name, service, slug, ev_path, extra_params in SECTIONS:
        # Platform count
        platform = fetch_platform_count(service, slug, hdrs, extra_params)

        # Local evidence
        local = scan_local(ev_path)

        # Notes
        notes = []
        if isinstance(platform, int) and local["total"] > 0:
            gap = local["pending"]
            if gap > 0:
                notes.append(f"{gap} to upload")
        if local["error"] > 0:
            notes.append(f"{local['error']} errors")
        if local["already"] > 0:
            notes.append(f"{local['already']} pre-existing")
        note_str = ", ".join(notes) if notes else ""

        rows.append((name, platform, local["total"], local["pending"], local["uploaded"], note_str))

        # Print row
        plat_disp = str(platform) if platform not in (None, "auth", "?") else ("🔒" if platform == "auth" else str(platform))
        loc_disp  = str(local["total"]) if local["total"] > 0 else "—"
        pend_disp = str(local["pending"]) if local["total"] > 0 else "—"
        up_disp   = str(local["uploaded"]) if local["total"] > 0 else "—"
        print(f"  {name:{col_w}}  {plat_disp:>8}  {loc_disp:>5}  {pend_disp:>7}  {up_disp:>8}  {note_str}")

    # Totals
    total_plat = sum(r[1] for r in rows if isinstance(r[1], int))
    total_loc  = sum(r[2] for r in rows)
    total_pend = sum(r[3] for r in rows)
    total_up   = sum(r[4] for r in rows)
    print(f"\n  {'─'*col_w}  {'─'*8}  {'─'*5}  {'─'*7}  {'─'*8}")
    print(f"  {'TOTAL':{col_w}}  {total_plat:>8}  {total_loc:>5}  {total_pend:>7}  {total_up:>8}")

    # Write markdown
    if WRITE_MD:
        LOG_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        md = render_report(rows, ts)
        REPORT_FILE.write_text(md, encoding="utf-8")
        print(f"\n  ✓ Report saved → {REPORT_FILE}")

    print()


if __name__ == "__main__":
    run()
