"""
rizoma-automation / 02_map_activities.py
=========================================
Phase 2: Navigate target sections and extract field schemas.

Target (scoped per CLAUDE.md):
  Trayectoria profesional >
    - Producción científica
    - Fortalecimiento y consolidación de la comunidad
    - Acceso universal al conocimiento

Outputs:
  config/schemas/{slug}.json          ← one per subsection found
  config/platform_structure.json      ← master section/field map
  logs/phase2_YYYYMMDD_HHMMSS.log     ← full timestamped run log
  logs/phase2_review.md               ← human-readable summary
  logs/phase2_structure.mmd           ← Mermaid diagram of section structure

Usage:
  python scripts/02_map_activities.py            # uses .env + saved session
  python scripts/02_map_activities.py --headless
  python scripts/02_map_activities.py --relogin  # force fresh login
"""

import asyncio
import json
import os
import re
import sys
import getpass
from pathlib import Path
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Page, BrowserContext

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv optional

BASE_URL = "https://rizoma.conahcyt.mx"
ROOT = Path(__file__).parent.parent
LOG_DIR = ROOT / "logs"
SESSION_DIR = ROOT / "session"
SCHEMA_DIR = ROOT / "config" / "schemas"
CONFIG_DIR = ROOT / "config"

for d in [LOG_DIR, SESSION_DIR, SCHEMA_DIR, CONFIG_DIR]:
    d.mkdir(exist_ok=True)

HEADLESS = "--headless" in sys.argv
RELOGIN  = "--relogin"  in sys.argv
SESSION_FILE = SESSION_DIR / "session_state.json"

# ── Run log (written to file + printed) ───────────────────────────────────────

_run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
_log_path = LOG_DIR / f"phase2_{_run_ts}.log"
_log_lines: list[str] = []

def log(msg: str = "", indent: int = 0):
    line = "  " * indent + msg
    print(line)
    _log_lines.append(line)

def flush_log():
    with open(_log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def slug(text: str) -> str:
    text = text.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ü","u")]:
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

# ── Target sections (hardcoded from requirements.md) ──────────────────────────
# Grouped by logical section. We ONLY touch these URLs.

TARGET_URLS: list[dict] = [
    # ── Producción científica-humanística ─────────────────────────────────────
    {"group": "Producción / Científica-humanística",     "slug": "articulos",                       "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/articulos"},
    {"group": "Producción / Científica-humanística",     "slug": "libros",                          "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/libros"},
    {"group": "Producción / Científica-humanística",     "slug": "capitulos",                       "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/capitulos"},
    {"group": "Producción / Científica-humanística",     "slug": "reportes",                        "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/reportes"},
    {"group": "Producción / Científica-humanística",     "slug": "informes",                        "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/informes"},
    {"group": "Producción / Científica-humanística",     "slug": "dossier_numero_tematico",         "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/dossier-o-numero-tematico"},
    {"group": "Producción / Científica-humanística",     "slug": "antologias",                      "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/antologias"},
    {"group": "Producción / Científica-humanística",     "slug": "traducciones",                    "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/traducciones"},
    {"group": "Producción / Científica-humanística",     "slug": "prologos_estudios_introductorios","url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/prologos-estudios-introductorios"},
    {"group": "Producción / Científica-humanística",     "slug": "curadurias",                      "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/curadurias"},
    {"group": "Producción / Científica-humanística",     "slug": "base_datos_primarios",            "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/base-datos-primarios"},
    # ── Aportaciones ─────────────────────────────────────────────────────────
    {"group": "Aportaciones",                            "slug": "desarrollos_tecnologicos",        "url": "https://rizoma.conahcyt.mx/aportaciones/desarrollos-tecnologicos-innovaciones"},
    {"group": "Aportaciones",                            "slug": "propiedades_intelectuales",       "url": "https://rizoma.conahcyt.mx/aportaciones/propiedades-intelectuales"},
    {"group": "Aportaciones",                            "slug": "transferencias_tecnologicas",     "url": "https://rizoma.conahcyt.mx/aportaciones/transferencias-tecnologicas"},
    {"group": "Aportaciones",                            "slug": "informes_tecnicos",               "url": "https://rizoma.conahcyt.mx/aportaciones/informes-tecnicos"},
    {"group": "Aportaciones",                            "slug": "proyectos_investigacion",         "url": "https://rizoma.conahcyt.mx/aportaciones/proyectos-investigacion"},
    {"group": "Aportaciones",                            "slug": "planes_estudio",                  "url": "https://rizoma.conahcyt.mx/aportaciones/planes-estudio"},
    {"group": "Aportaciones",                            "slug": "colaboraciones_interinstitucionales","url": "https://rizoma.conahcyt.mx/aportaciones/colaboraciones-interinstitucionales"},
    {"group": "Aportaciones",                            "slug": "coordinaciones",                  "url": "https://rizoma.conahcyt.mx/aportaciones/coordinaciones"},
    {"group": "Aportaciones",                            "slug": "jurados",                         "url": "https://rizoma.conahcyt.mx/aportaciones/jurados"},
    {"group": "Aportaciones",                            "slug": "evaluaciones_programas_proyectos","url": "https://rizoma.conahcyt.mx/aportaciones/evaluaciones-programas-proyectos"},
    {"group": "Aportaciones",                            "slug": "dictaminaciones_publicaciones",   "url": "https://rizoma.conahcyt.mx/aportaciones/dictaminaciones-publicaciones"},
    {"group": "Aportaciones",                            "slug": "dictaminaciones_especializadas",  "url": "https://rizoma.conahcyt.mx/aportaciones/dictaminaciones-especializadas"},
    # ── Fortalecimiento / Formación de la comunidad ───────────────────────────
    {"group": "Fortalecimiento / Docencia",              "slug": "cursos_impartidos",               "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/cursos-impartidos"},
    {"group": "Fortalecimiento / Docencia",              "slug": "diplomados_impartidos",           "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/diplomados-impartidos"},
    {"group": "Fortalecimiento / Docencia",              "slug": "capacitaciones",                  "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/capacitaciones"},
    {"group": "Fortalecimiento / Docencia",              "slug": "talleres",                        "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/talleres"},
    {"group": "Fortalecimiento / Docencia",              "slug": "seminarios",                      "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/seminarios"},
    {"group": "Fortalecimiento / Docencia",              "slug": "tutorias",                        "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/tutorias"},
    {"group": "Fortalecimiento",                         "slug": "trabajos_titulacion",             "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/trabajos-titulacion"},
    {"group": "Fortalecimiento",                         "slug": "editorial",                       "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/editorial"},
    # ── Estancias ─────────────────────────────────────────────────────────────
    {"group": "Estancias",                               "slug": "estancias_investigacion",         "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/estancias-investigacion"},
    # ── Acceso universal al conocimiento ─────────────────────────────────────
    {"group": "Acceso universal al conocimiento",        "slug": "medios_escritos",                 "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/medios-escritos"},
    {"group": "Acceso universal al conocimiento",        "slug": "audiovisuales_radiofonicos",      "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/audiovisuales-radiofonicos-digitales"},
    {"group": "Acceso universal al conocimiento",        "slug": "museografia",                     "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/museografia-espacios-educacion-no-formal"},
    {"group": "Acceso universal al conocimiento",        "slug": "eventos_comunicacion",            "url": "https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/eventos-comunicacion"},
]

# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_credentials() -> tuple[str, str]:
    username = os.getenv("RIZOMA_USER", "")
    password = os.getenv("RIZOMA_PASSWORD", "")
    if not username:
        username = input("  Usuario (email o CURP): ").strip()
    else:
        log(f"  ✓ Username loaded from .env: {username}")
    if not password:
        password = getpass.getpass("  Contraseña: ")
    else:
        log("  ✓ Password loaded from .env")
    return username, password

async def wait_for_app(page: Page):
    """Wait for the JHipster/Vue loading overlay to disappear."""
    log("  → Waiting for app to mount (loading overlay)...", indent=0)
    try:
        await page.wait_for_selector("#jhipster-loading", state="hidden", timeout=30000)
        log("  ✓ App mounted (loading overlay gone)")
    except Exception:
        log("  ⚠ Timeout waiting for loading overlay — continuing anyway")
    await page.wait_for_timeout(2000)  # extra buffer for Vue to finish rendering

async def dismiss_popup(page: Page):
    """Dismiss the initial privacy/announcement popup if present."""
    log("  → Checking for initial popup...")
    # Common popup dismiss patterns — update button text once requirements.md is filled
    popup_selectors = [
        'button:has-text("Aceptar")',
        'button:has-text("Cerrar")',
        'button:has-text("Entendido")',
        'button:has-text("Continuar")',
        'button:has-text("OK")',
        '[aria-label="Close"]',
        '.modal-footer button',
        '.swal2-confirm',   # SweetAlert2 (common in JHipster apps)
        '.btn-close',
    ]
    for sel in popup_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=800):
                text = await el.inner_text()
                await el.click()
                await page.wait_for_timeout(800)
                log(f"  ✓ Dismissed popup via: {sel!r} (text: {text.strip()!r})")
                return
        except Exception:
            pass
    log("  · No popup found (or already dismissed)")

async def login(page: Page, username: str, password: str):
    """Full OAuth2/Keycloak login flow."""
    log(f"  → Navigating to {BASE_URL} ...")
    await page.goto(BASE_URL, timeout=30000)
    await wait_for_app(page)

    for sel in ['button:has-text("Iniciar sesión")', 'a:has-text("Iniciar sesión")', 'a[href*="login"]']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                async with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    await el.click()
                break
        except Exception:
            continue

    await page.wait_for_timeout(2000)

    for sel in ['input[name="username"]', 'input[id="username"]', 'input[type="email"]']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await page.fill(sel, username)
                break
        except Exception:
            continue

    for sel in ['input[name="password"]', 'input[id="password"]', 'input[type="password"]']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await page.fill(sel, password)
                break
        except Exception:
            continue

    for sel in ['input[type="submit"]', 'button[type="submit"]', 'button:has-text("Acceder")']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                await el.click()
                break
        except Exception:
            continue

    await page.wait_for_timeout(4000)
    try:
        await page.wait_for_url("**/rizoma.conahcyt.mx/**", timeout=20000)
    except Exception:
        pass
    await wait_for_app(page)
    log(f"  ✓ Post-login URL: {page.url}")

# ── Network capture ───────────────────────────────────────────────────────────

def attach_capture(page: Page, captured: list):
    async def on_request(req):
        from urllib.parse import urlparse
        if req.resource_type in ("fetch", "xhr"):
            entry = {"method": req.method, "url": req.url, "path": urlparse(req.url).path}
            try:
                body = req.post_data
                if body:
                    try:
                        entry["body_shape"] = {k: type(v).__name__ for k, v in json.loads(body).items()}
                    except Exception:
                        entry["body_raw"] = body[:300]
            except Exception:
                pass
            captured.append(entry)

    async def on_response(resp):
        if resp.request.resource_type in ("fetch", "xhr"):
            for entry in captured:
                if entry["url"] == resp.url and "status" not in entry:
                    entry["status"] = resp.status
                    try:
                        ct = resp.headers.get("content-type", "")
                        if "json" in ct:
                            body = await resp.json()
                            if isinstance(body, dict):
                                entry["response_keys"] = list(body.keys())
                                entry["response_size"] = len(body)
                            elif isinstance(body, list):
                                entry["response_count"] = len(body)
                                if body and isinstance(body[0], dict):
                                    entry["response_item_keys"] = list(body[0].keys())
                    except Exception:
                        pass
                    break

    page.on("request", on_request)
    page.on("response", on_response)

# ── Nav discovery ─────────────────────────────────────────────────────────────

def build_nav_items() -> list[dict]:
    """Convert TARGET_URLS into nav_item dicts for map_section()."""
    items = []
    for entry in TARGET_URLS:
        path = entry["url"].split("rizoma.conahcyt.mx")[1]
        # Use last path segment as display text (slug → readable)
        name = path.rstrip("/").split("/")[-1].replace("-", " ").title()
        items.append({
            "text": name,
            "href": entry["url"],
            "path": path,
            "group": entry["group"],
            "slug": entry["slug"],
        })
    return items

# ── Form extraction ───────────────────────────────────────────────────────────

async def extract_form_fields(page: Page) -> list[dict]:
    return await page.evaluate("""() => {
        const results = [];
        document.querySelectorAll(
            'input:not([type="hidden"]), select, textarea, [role="combobox"], [role="spinbutton"]'
        ).forEach(el => {
            if (el.offsetWidth === 0 || el.offsetHeight === 0) return;
            const label = (() => {
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl) return lbl.innerText.trim();
                }
                // walk up to find a label sibling
                let p = el.parentElement;
                for (let i = 0; i < 4; i++) {
                    if (!p) break;
                    const lbl = p.querySelector('label');
                    if (lbl && lbl !== el) return lbl.innerText.trim();
                    p = p.parentElement;
                }
                return el.placeholder || el.name || el.id || null;
            })();
            results.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                name: el.name || null,
                id: el.id || null,
                label: label,
                required: el.required || el.getAttribute('aria-required') === 'true',
                options: el.tagName === 'SELECT'
                    ? Array.from(el.options)
                        .map(o => ({value: o.value, text: o.text.trim()}))
                        .filter(o => o.value && o.value !== '')
                    : null,
            });
        });
        return results;
    }""")

async def extract_headings(page: Page) -> list[str]:
    return await page.evaluate("""() =>
        Array.from(document.querySelectorAll('h1,h2,h3,.card-title,.page-title,.section-title'))
            .filter(el => el.offsetWidth > 0)
            .map(el => el.innerText.trim())
            .filter(t => t.length > 0 && t.length < 150)
    """)

# ── Section mapper ────────────────────────────────────────────────────────────

async def map_section(page: Page, nav_item: dict, idx: int) -> dict:
    href  = nav_item["href"]
    text  = nav_item["text"]
    sslug = nav_item.get("slug") or slug(text)
    group = nav_item.get("group", "")

    log(f"\n{'─'*60}")
    log(f"  [{idx:02d}] {group} › {text}")
    log(f"        URL: {href}")

    captured = []
    attach_capture(page, captured)

    result = {
        "group": group,
        "subsection": text,
        "slug": sslug,
        "url": href,
        "mapped_at": now_iso(),
        "list_api_calls": [],
        "form_api_calls": [],
        "form_fields": [],
        "headings": [],
        "add_form_found": False,
        "notes": [],
    }

    try:
        await page.goto(href, wait_until="domcontentloaded", timeout=20000)
        await wait_for_app(page)
        await dismiss_popup(page)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(LOG_DIR / f"phase2_{idx:02d}_{sslug}_list.png"))

        result["headings"] = await extract_headings(page)
        log(f"        Headings: {result['headings']}")

        # Filter to useful API calls
        noise = {"sentry", "analytics", "g/collect", "management/info",
                 "i18n", "/api/account", "sentry/config", "gtm"}
        result["list_api_calls"] = [
            c for c in captured
            if "rizoma.conahcyt.mx" in c.get("url","")
            and not any(n in c.get("url","") for n in noise)
        ]
        log(f"        API calls on list view: {len(result['list_api_calls'])}")
        for c in result["list_api_calls"]:
            keys = c.get("response_keys") or c.get("response_item_keys") or []
            status = c.get("status","?")
            log(f"          {c['method']:6s} {c['path']}  [{status}]  keys={keys}", indent=2)

        # ── Try to open add form ──────────────────────────────────────────────
        captured_form = []
        attach_capture(page, captured_form)

        add_selectors = [
            'button:has-text("Agregar")',
            'a:has-text("Agregar")',
            'button:has-text("Nuevo")',
            'button:has-text("Nueva")',
            'button[title="Agregar"]',
            '.btn-primary:has-text("Agregar")',
        ]
        for sel in add_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    await page.wait_for_timeout(2500)
                    await wait_for_app(page)
                    result["add_form_found"] = True
                    log(f"        ✓ Opened form via: {sel!r}")
                    break
            except Exception:
                pass

        if result["add_form_found"]:
            await page.screenshot(path=str(LOG_DIR / f"phase2_{idx:02d}_{sslug}_form.png"))
            result["form_fields"] = await extract_form_fields(page)
            log(f"        Form fields ({len(result['form_fields'])}):")
            for f in result["form_fields"]:
                req = " [required]" if f.get("required") else ""
                opts = f" options={[o['text'] for o in f['options'][:5]]}" if f.get("options") else ""
                log(f"          {f['tag']:10s} name={f.get('name') or f.get('id')!r:30s} label={f.get('label')!r}{req}{opts}", indent=2)

            result["form_api_calls"] = [
                c for c in captured_form
                if "rizoma.conahcyt.mx" in c.get("url","")
                and not any(n in c.get("url","") for n in noise)
            ]

            # Close without submitting
            for close_sel in ['button:has-text("Cancelar")', 'button:has-text("Cerrar")',
                               'button[aria-label="Close"]', '.modal .close', '.btn-close']:
                try:
                    el = page.locator(close_sel).first
                    if await el.is_visible(timeout=800):
                        await el.click()
                        await page.wait_for_timeout(500)
                        break
                except Exception:
                    pass
        else:
            note = "No 'Agregar' button found"
            result["notes"].append(note)
            log(f"        ⚠ {note}")

        # Save schema immediately
        save_json(SCHEMA_DIR / f"{sslug}.json", result)
        log(f"        ✓ Saved config/schemas/{sslug}.json")

    except Exception as e:
        result["notes"].append(f"Error: {e}")
        log(f"        ✗ Error: {e}")
        try:
            await page.screenshot(path=str(LOG_DIR / f"phase2_{idx:02d}_{sslug}_error.png"))
        except Exception:
            pass

    return result

# ── Mermaid diagram ───────────────────────────────────────────────────────────

def write_mermaid(schemas: list[dict]):
    lines = [
        "flowchart TD",
        '    ROOT["rizoma.conahcyt.mx"]',
    ]
    # Collect unique groups
    groups_seen: dict[str, str] = {}  # group_label -> node_id
    for s in schemas:
        g = s.get("group", "Other")
        g_id = slug(g)
        if g_id not in groups_seen:
            groups_seen[g_id] = g
            lines.append(f'    ROOT --> {g_id}["{g}"]')
        node_id = s["slug"]
        label = s["subsection"].replace('"', "'")
        lines.append(f'    {g_id} --> {node_id}["{label}"]')
        for i, f in enumerate(s.get("form_fields", [])[:6]):
            fname = (f.get("label") or f.get("name") or "?").replace('"', "'")
            lines.append(f'    {node_id} --> {node_id}_f{i}("{fname}")')
    with open(LOG_DIR / "phase2_structure.mmd", "w", encoding="utf-8") as f:
        f.write("```mermaid\n" + "\n".join(lines) + "\n```")

# ── Review MD ─────────────────────────────────────────────────────────────────

def write_review(schemas: list[dict]):
    lines = [
        "# Phase 2 — Section/Field Mapping Review",
        f"Generated: {now_iso()}",
        f"Log: `logs/phase2_{_run_ts}.log`",
        "",
        f"**Sections mapped:** {len(schemas)}  ",
        f"**Sections with add form:** {sum(1 for s in schemas if s['add_form_found'])}",
        "",
    ]

    # Mermaid diagram inline
    lines += [
        "## Structure diagram",
        "",
        "```mermaid",
        "flowchart LR",
        '    TP["Trayectoria profesional"]',
    ]
    for s in schemas:
        nid = s["slug"].replace("-","_")
        lines.append(f'    TP --> {nid}["{s["subsection"]}"]')
        for i, f in enumerate(s.get("form_fields", [])[:6]):
            fname = (f.get("label") or f.get("name") or "?").replace('"',"'")
            lines.append(f'    {nid} --> {nid}_f{i}("{fname}")')
    lines += ["```", ""]

    lines.append("---")
    lines.append("")

    current_group = None
    for s in schemas:
        g = s.get("group", "Other")
        if g != current_group:
            current_group = g
            lines.append(f"## {g}")
            lines.append("")
        lines.append(f"### {s['subsection']}")
        lines.append(f"- **URL:** `{s['url']}`")
        lines.append(f"- **Slug:** `{s['slug']}`")
        lines.append(f"- **Add form:** {'✅' if s['add_form_found'] else '❌'}")
        if s.get("headings"):
            lines.append(f"- **Page headings:** {', '.join(repr(h) for h in s['headings'][:4])}")

        if s.get("list_api_calls"):
            lines.append("")
            lines.append("### API — list view")
            lines.append("| Method | Path | Status | Response keys |")
            lines.append("|--------|------|--------|---------------|")
            for c in s["list_api_calls"]:
                keys = c.get("response_keys") or c.get("response_item_keys") or []
                lines.append(f"| `{c['method']}` | `{c['path']}` | {c.get('status','')} | `{', '.join(str(k) for k in keys[:10])}` |")

        if s.get("form_fields"):
            lines.append("")
            lines.append("### Form fields")
            lines.append("| Name | Label | Type | Required | Options |")
            lines.append("|------|-------|------|----------|---------|")
            for f in s["form_fields"]:
                name = f.get("name") or f.get("id") or "—"
                label = f.get("label") or "—"
                ftype = f.get("type") or f.get("tag") or "—"
                req = "✅" if f.get("required") else ""
                opts = ", ".join(o["text"] for o in (f.get("options") or [])[:4])
                lines.append(f"| `{name}` | {label} | {ftype} | {req} | {opts} |")

            if s.get("form_api_calls"):
                lines.append("")
                lines.append("### API — form open (catalogs/dropdowns)")
                lines.append("| Method | Path | Status | Keys |")
                lines.append("|--------|------|--------|------|")
                for c in s["form_api_calls"]:
                    keys = c.get("response_keys") or c.get("response_item_keys") or []
                    lines.append(f"| `{c['method']}` | `{c['path']}` | {c.get('status','')} | `{', '.join(str(k) for k in keys[:8])}` |")

        if s.get("notes"):
            lines.append("")
            lines.append(f"> **Notes:** {'; '.join(s['notes'])}")

        lines += ["", "---", ""]

    with open(LOG_DIR / "phase2_review.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ── Main ──────────────────────────────────────────────────────────────────────

async def run():
    log("╔══════════════════════════════════════════╗")
    log("║  Rizoma Mapper — Phase 2: Field Schemas  ║")
    log("╚══════════════════════════════════════════╝")
    log(f"  Run: {_run_ts}")

    use_session = SESSION_FILE.exists() and not RELOGIN
    username = password = ""

    if use_session:
        log(f"  ✓ Saved session found (--relogin to force fresh login)")
    else:
        log("  No saved session — will log in")
        username, password = get_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, slow_mo=120)
        ctx_args = dict(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        if use_session:
            ctx_args["storage_state"] = str(SESSION_FILE)

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()

        # ── Auth ──────────────────────────────────────────────────────────────
        if use_session:
            log("  → Loading with saved session...")
            await page.goto(BASE_URL, timeout=30000)
            await wait_for_app(page)
            if "idm.conahcyt.mx" in page.url or "/login" in page.url:
                log("  ⚠ Session expired — run with --relogin")
                await browser.close()
                return
            log(f"  ✓ Session valid — {page.url}")
        else:
            await login(page, username, password)
            await context.storage_state(path=str(SESSION_FILE))
            log("  ✓ Session saved")

        await dismiss_popup(page)
        await page.screenshot(path=str(LOG_DIR / "phase2_00_dashboard.png"))

        # ── Build section list from hardcoded URLs ────────────────────────────
        nav_items = build_nav_items()
        log(f"\n  → {len(nav_items)} target sections to map:")
        for item in nav_items:
            log(f"    [{item['group']:45s}] {item['slug']}")

        # ── Map each section ──────────────────────────────────────────────────
        all_schemas = []
        for i, item in enumerate(nav_items):
            schema = await map_section(page, item, i + 1)
            all_schemas.append(schema)

        # ── Save outputs ──────────────────────────────────────────────────────
        save_json(CONFIG_DIR / "platform_structure.json", {
            "generated_at": now_iso(),
            "target": "Trayectoria profesional",
            "sections_mapped": len(all_schemas),
            "sections": all_schemas,
        })

        await context.storage_state(path=str(SESSION_FILE))
        await browser.close()

    write_mermaid(all_schemas)
    write_review(all_schemas)
    flush_log()

    log(f"\n{'═'*60}")
    log(f"  ✓ {len(all_schemas)} sections mapped")
    log(f"  ✓ config/platform_structure.json")
    log(f"  ✓ config/schemas/  ({len(all_schemas)} files)")
    log(f"  ✓ logs/phase2_review.md")
    log(f"  ✓ logs/phase2_structure.mmd  (Mermaid)")
    log(f"  ✓ logs/phase2_{_run_ts}.log  (full run log)")
    log(f"  Next: review phase2_review.md, then build 03_upload.py")


if __name__ == "__main__":
    asyncio.run(run())
