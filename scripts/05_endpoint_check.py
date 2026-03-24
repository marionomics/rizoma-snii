"""
rizoma-automation / 05_endpoint_check.py
=========================================
Probe every known + candidate API endpoint to verify which ones still respond
correctly after a platform update.

What this script does:
  1. Loads session cookies from session/session_state.json
  2. Sends a GET request to each endpoint (known + candidate discovery list)
  3. Prints a status table: ✓ 200, ✗ 404, ⚠ other, 🔒 401/403
  4. Saves full results to logs/endpoint_check.json

Usage:
  python scripts/05_endpoint_check.py

If the session has expired, you'll see 🔒 401 on every endpoint.
Re-run scripts/01_recon.py first to refresh session/session_state.json, then
run this script again.
"""

import json
import sys
import ssl
import time
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error
import http.cookiejar

# Rizoma uses a certificate chain that Python can't verify locally.
# We're only doing read-only GET probes on a known URL — unverified is fine here.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

BASE_URL = "https://rizoma.conahcyt.mx"
APORTACIONES = f"{BASE_URL}/services/msaportaciones/api"
PERFIL       = f"{BASE_URL}/services/msperfil/api"
SACI         = f"{BASE_URL}/services/saci/api/v1"

SESSION_FILE = Path(__file__).parent.parent / "session" / "session_state.json"
LOG_DIR      = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Endpoint definitions ──────────────────────────────────────────────────────

# All 36 sections we have schemas for
KNOWN_ENDPOINTS = [
    # Producción / Científica-humanística
    ("GET", f"{APORTACIONES}/articulos?page=1&size=1",                        "articulos"),
    ("GET", f"{APORTACIONES}/libros?page=1&size=1",                           "libros"),
    ("GET", f"{APORTACIONES}/capitulos?page=1&size=1",                        "capitulos"),
    ("GET", f"{APORTACIONES}/reportes?page=1&size=1",                         "reportes"),
    ("GET", f"{APORTACIONES}/informes?page=1&size=1",                         "informes"),
    ("GET", f"{APORTACIONES}/dossier-o-numero-tematico?page=1&size=1",         "dossier-o-numero-tematico"),
    ("GET", f"{APORTACIONES}/antologias?page=1&size=1",                       "antologias"),
    ("GET", f"{APORTACIONES}/traducciones?page=1&size=1",                     "traducciones"),
    ("GET", f"{APORTACIONES}/prologos-estudios-introductorios?page=1&size=1", "prologos-estudios-introductorios"),
    ("GET", f"{APORTACIONES}/curadurias?page=1&size=1",                       "curadurias"),
    ("GET", f"{APORTACIONES}/base-datos-primarios?page=1&size=1",             "base-datos-primarios"),
    # Aportaciones
    ("GET", f"{APORTACIONES}/desarrollos-tecnologicos-innovaciones?page=1&size=1",      "desarrollos-tecnologicos-innovaciones"),
    ("GET", f"{APORTACIONES}/propiedades-intelectuales?page=1&size=1",                 "propiedades-intelectuales"),
    ("GET", f"{APORTACIONES}/transferencias-tecnologicas?page=1&size=1",               "transferencias-tecnologicas"),
    ("GET", f"{APORTACIONES}/informes-tecnicos?page=1&size=1",                         "informes-tecnicos"),
    ("GET", f"{APORTACIONES}/proyectos-investigacion?page=1&size=1",                   "proyectos-investigacion"),
    ("GET", f"{APORTACIONES}/planes-estudio?page=1&size=1",                            "planes-estudio"),
    ("GET", f"{APORTACIONES}/colaboraciones-interinstitucionales?page=1&size=1",       "colaboraciones-interinstitucionales"),
    ("GET", f"{APORTACIONES}/coordinaciones?page=1&size=1",                            "coordinaciones"),
    ("GET", f"{APORTACIONES}/jurados?page=1&size=1",                                   "jurados"),
    ("GET", f"{APORTACIONES}/evaluaciones-programas-proyectos?page=1&size=1",          "evaluaciones-programas-proyectos"),
    ("GET", f"{APORTACIONES}/dictaminaciones-publicaciones?page=1&size=1",             "dictaminaciones-publicaciones"),
    ("GET", f"{APORTACIONES}/dictaminaciones-especializadas?page=1&size=1",            "dictaminaciones-especializadas"),
    # Fortalecimiento / Formación
    ("GET", f"{PERFIL}/cursos-impartidos?page=1&size=1",                               "msperfil/cursos-impartidos"),
    ("GET", f"{PERFIL}/diplomados?page=1&size=1",                                      "msperfil/diplomados"),
    ("GET", f"{APORTACIONES}/capacitaciones?page=1&size=1",                            "capacitaciones"),
    ("GET", f"{APORTACIONES}/talleres?page=1&size=1",                                  "talleres"),
    ("GET", f"{APORTACIONES}/seminarios?page=1&size=1",                                "seminarios"),
    ("GET", f"{APORTACIONES}/tutorias?page=1&size=1",                                  "tutorias"),
    ("GET", f"{PERFIL}/tesis?page=1&size=1",                                           "msperfil/tesis"),
    ("GET", f"{APORTACIONES}/participacion-editorial?page=1&size=1",                    "participacion-editorial"),
    # Estancias
    ("GET", f"{PERFIL}/estancias?page=1&size=1",                                       "msperfil/estancias"),
    # Acceso universal
    ("GET", f"{APORTACIONES}/medios-escritos?page=1&size=1",                           "medios-escritos"),
    ("GET", f"{APORTACIONES}/audiovisuales-radiofonicos-digitales?page=1&size=1",       "audiovisuales-radiofonicos-digitales"),
    ("GET", f"{APORTACIONES}/museografia-espacios-educacion-no-formal?page=1&size=1",  "museografia-espacios-educacion-no-formal"),
    ("GET", f"{APORTACIONES}/eventos-comunicacion?page=1&size=1",                      "eventos-comunicacion"),
]

# Candidate endpoints from i18n keys / old platform memory — not in any schema yet
CANDIDATE_ENDPOINTS = [
    # Possible renamed / split sections
    ("GET", f"{APORTACIONES}/memorias-congresos?page=1&size=1",               "? memorias-congresos"),
    ("GET", f"{APORTACIONES}/participacion-congresos?page=1&size=1",          "? participacion-congresos"),
    ("GET", f"{APORTACIONES}/congresos?page=1&size=1",                        "? congresos"),
    ("GET", f"{APORTACIONES}/divulgacion?page=1&size=1",                      "? divulgacion"),
    ("GET", f"{APORTACIONES}/articulos-difusion?page=1&size=1",               "? articulos-difusion"),
    ("GET", f"{APORTACIONES}/libros-difusion?page=1&size=1",                  "? libros-difusion"),
    ("GET", f"{APORTACIONES}/capitulos-difusion?page=1&size=1",               "? capitulos-difusion"),
    ("GET", f"{APORTACIONES}/guiones?page=1&size=1",                          "? guiones"),
    ("GET", f"{APORTACIONES}/innovaciones?page=1&size=1",                     "? innovaciones"),
    ("GET", f"{APORTACIONES}/desarrollos-software?page=1&size=1",             "? desarrollos-software"),
    ("GET", f"{APORTACIONES}/patentes?page=1&size=1",                         "? patentes"),
    ("GET", f"{APORTACIONES}/becas-nacionales?page=1&size=1",                 "? becas-nacionales"),
    ("GET", f"{APORTACIONES}/invitaciones-destacadas?page=1&size=1",          "? invitaciones-destacadas"),
    ("GET", f"{APORTACIONES}/grupos?page=1&size=1",                           "? grupos"),
    ("GET", f"{APORTACIONES}/tesis?page=1&size=1",                            "? tesis"),
    # Alternate slug forms for existing sections
    ("GET", f"{APORTACIONES}/dossier?page=1&size=1",                          "? dossier (alt)"),
    ("GET", f"{APORTACIONES}/prologos?page=1&size=1",                         "? prologos (alt)"),
    ("GET", f"{APORTACIONES}/audiovisuales?page=1&size=1",                    "? audiovisuales (alt)"),
    ("GET", f"{APORTACIONES}/audiovisuales-radiofonicos-digitales?page=1&size=1", "? audiovisuales-radiofonicos-digitales (alt)"),
    ("GET", f"{APORTACIONES}/museografia-espacios-educacion-no-formal?page=1&size=1", "? museografia-espacios (alt)"),
]

# Infrastructure / support endpoints
INFRA_ENDPOINTS = [
    ("GET", f"{BASE_URL}/management/info",                                     "mgmt/info"),
    ("GET", f"{BASE_URL}/api/account",                                         "gateway/account"),
    ("GET", f"{PERFIL}/mi-perfil/valida",                                      "msperfil/mi-perfil/valida"),
    ("GET", f"{PERFIL}/soluciones?page=1&size=5",                              "msperfil/soluciones"),
    ("GET", f"{APORTACIONES}/total-documentos/con-documento",                  "msaportaciones/total-docs"),
    ("GET", f"{PERFIL}/total-productos/items-con-documento",                   "msperfil/total-productos"),
    ("GET", f"{SACI}/tipos-participacion?page=1&size=5",                       "saci/tipos-participacion"),
    ("GET", f"{SACI}/catalogos-maestros/23/catalogos-detalle?page=1&size=5",  "saci/catalogo-23"),
]

# ── Cookie loader ─────────────────────────────────────────────────────────────

def load_cookies() -> dict:
    """Extract rizoma.conahcyt.mx cookies from Playwright session_state.json."""
    if not SESSION_FILE.exists():
        print(f"  ✗ Session file not found: {SESSION_FILE}")
        print("    Run scripts/01_recon.py first.")
        sys.exit(1)

    state = json.loads(SESSION_FILE.read_text())
    cookies = {}
    xsrf = None
    for c in state.get("cookies", []):
        if "rizoma.conahcyt.mx" in c.get("domain", "") or c.get("domain") == "rizoma.conahcyt.mx":
            cookies[c["name"]] = c["value"]
            if c["name"] == "XSRF-TOKEN":
                xsrf = c["value"]
    return cookies, xsrf


def make_request(url: str, cookies: dict, xsrf: str | None) -> tuple[int, dict | list | None]:
    """Make a GET request with the session cookies. Returns (status_code, body)."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Accept-Language", "es-419,es;q=0.9")
    req.add_header("User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Build Cookie header
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req.add_header("Cookie", cookie_str)
    if xsrf:
        req.add_header("X-XSRF-TOKEN", xsrf)

    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            status = resp.status
            try:
                body = json.loads(resp.read().decode("utf-8"))
            except Exception:
                body = None
            return status, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def status_icon(code: int) -> str:
    if code == 200:   return "✓"
    if code in (401, 403): return "🔒"
    if code == 404:   return "✗"
    if code == 0:     return "⚡"
    return "⚠"


def body_summary(body, code: int) -> str:
    if body is None:
        return ""
    if isinstance(body, list):
        return f"({len(body)} items)"
    if isinstance(body, dict):
        if code == 200:
            keys = list(body.keys())[:4]
            return f"keys: {keys}"
        if "message" in body:
            return body["message"][:60]
        if "detail" in body:
            return body["detail"][:60]
    return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   Rizoma Endpoint Check — Phase 0 (re-validation)            ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    cookies, xsrf = load_cookies()
    print(f"  Loaded {len(cookies)} cookies for rizoma.conahcyt.mx")
    print(f"  XSRF-TOKEN: {'present' if xsrf else 'missing'}\n")

    results = []
    auth_failed = 0

    def probe_group(label: str, endpoints: list):
        nonlocal auth_failed
        print(f"\n  ── {label} {'─' * (55 - len(label))}")
        print(f"  {'St':>4}  {'Endpoint':<50}  Info")
        print(f"  {'----':>4}  {'--------------------------------------------------':<50}  ----")
        for method, url, name in endpoints:
            code, body = make_request(url, cookies, xsrf)
            icon = status_icon(code)
            info = body_summary(body, code)
            print(f"  {icon} {code:>3}  {name:<50}  {info}")
            results.append({
                "name": name,
                "method": method,
                "url": url,
                "status": code,
                "body_summary": info,
                "changed": code not in (200,),
            })
            if code in (401, 403):
                auth_failed += 1
            time.sleep(0.15)  # gentle rate limiting

    probe_group("Infrastructure / support", INFRA_ENDPOINTS)
    probe_group("Known endpoints (36 sections)", KNOWN_ENDPOINTS)
    probe_group("Candidate / new endpoints", CANDIDATE_ENDPOINTS)

    # ── Summary ───────────────────────────────────────────────────────────────
    ok      = [r for r in results if r["status"] == 200]
    missing = [r for r in results if r["status"] == 404]
    auth_e  = [r for r in results if r["status"] in (401, 403)]
    other   = [r for r in results if r["status"] not in (200, 404, 401, 403)]
    new_ok  = [r for r in results if r["status"] == 200 and r["name"].startswith("?")]

    print(f"\n  ══════════════════ SUMMARY ══════════════════")
    print(f"  ✓ OK (200):       {len(ok):>3}")
    print(f"  ✗ Not found (404):{len(missing):>3}")
    print(f"  🔒 Auth error:    {len(auth_e):>3}")
    print(f"  ⚠ Other:          {len(other):>3}")

    if new_ok:
        print(f"\n  🆕 NEW endpoints that responded 200:")
        for r in new_ok:
            print(f"      {r['name']}")

    if missing:
        print(f"\n  ✗ Missing endpoints (404):")
        for r in missing:
            print(f"      {r['name']}")

    if auth_failed > len(results) * 0.5:
        print("\n  ⚠️  More than half of requests returned 401/403.")
        print("     Your session has likely expired.")
        print("     → Re-run scripts/01_recon.py to refresh session/session_state.json")

    # ── Save ──────────────────────────────────────────────────────────────────
    output = {
        "checked_at": datetime.utcnow().isoformat(),
        "total": len(results),
        "ok": len(ok),
        "not_found": len(missing),
        "auth_error": len(auth_e),
        "other_error": len(other),
        "new_endpoints_found": [r["name"] for r in new_ok],
        "missing_endpoints": [r["name"] for r in missing],
        "results": results,
    }
    out_path = LOG_DIR / "endpoint_check.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n  Full results saved → logs/endpoint_check.json\n")


if __name__ == "__main__":
    run()
