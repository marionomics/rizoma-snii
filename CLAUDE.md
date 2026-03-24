# CLAUDE.md — Rizoma Automation Project

## What this project is

Semi-automated tooling for managing **SNII evidence on rizoma.conahcyt.mx** (CONAHCYT's Perfil Único / CVU platform). The goal is to:

1. **Map** the platform's full section/subsection/field structure
2. **Track** all evidence items as local JSON + paired PDF files
3. **Automate** uploading metadata and documents via the platform's API
4. **Maintain checklists** so every item has a clear status

The platform user is a researcher with an active SNII account on rizoma.conahcyt.mx.

---

## Auth context

- Login button on homepage triggers a redirect to Keycloak / OpenID Connect:
  `https://idm.conahcyt.mx/auth/realms/conacyt/protocol/openid-connect/auth?...`
- After auth, the browser is redirected back to `http://rizoma.conahcyt.mx/login/oauth2/code/oidc`
- This is an **OAuth2 Authorization Code flow** — not a simple form POST
- Playwright must follow the full redirect chain and handle the Keycloak login form
- Session tokens/cookies are saved to `session/session_state.json` (gitignored)
- Credentials stored in `.env` (gitignored): `RIZOMA_USER`, `RIZOMA_PASSWORD`

### Critical: JHipster/Vue loading
Rizoma is a JHipster SPA. `wait_for_load_state("networkidle")` fires while the app is still on
the loading screen. Always wait for the overlay to disappear before interacting:
```python
await page.wait_for_selector("#jhipster-loading", state="hidden", timeout=30000)
```

---

## API architecture (confirmed Phase 1 & 2)

Three microservices behind `rizoma.conahcyt.mx/services/`:

| Service | Base path | Purpose |
|---------|-----------|---------|
| `msaportaciones` | `/services/msaportaciones/api/` | Activity records (artículos, libros, etc.) |
| `msperfil` | `/services/msperfil/api/` | Profile / personal data |
| `saci` | `/services/saci/api/v1/` | Catalog dropdowns (tipos, catálogos-maestros) |

**List endpoint pattern:** `GET /services/msaportaciones/api/{section}?page=1&size=25&...`
**Dropdown IDs come from:** `GET /services/saci/api/v1/catalogos-maestros/{id}/catalogos-detalle`
> ⚠️ Select values in forms render as `[object Object]` — never use the display string.
> Always POST the catalog `id` fetched from `saci`.

---

## Upload flow (confirmed two-step)

The `documento` field in list responses confirms **two-step upload** for all sections:
1. `POST` metadata → item gets an `id` in the system
2. `POST/PUT` file to a separate endpoint using that `id`

**Existing data:** 11 artículos already exist in Mario's account (do not duplicate).

---

## Platform structure (Phase 2 re-mapped 2026-03-23 — 36 sections confirmed)

Full field details in `config/schemas/{slug}.json` and `logs/platform_review.md`.

### API endpoint changes (platform update detected 2026-03-23)

| Schema slug | Old API endpoint | New API endpoint | Service |
|-------------|-----------------|------------------|---------|
| `dossier_numero_tematico` | `dossier-numero-tematico` | `dossier-o-numero-tematico` | msaportaciones |
| `desarrollos_tecnologicos` | `desarrollos-tecnologicos` | `desarrollos-tecnologicos-innovaciones` | msaportaciones |
| `editorial` | `editorial` | `participacion-editorial` | msaportaciones |
| `audiovisuales_radiofonicos` | `audiovisuales-radiofonicos` | `audiovisuales-radiofonicos-digitales` | msaportaciones |
| `museografia` | `museografia` | `museografia-espacios-educacion-no-formal` | msaportaciones |
| `cursos_impartidos` | `msaportaciones/cursos-impartidos` | `msperfil/cursos-impartidos` | **msperfil** |
| `diplomados_impartidos` | `msaportaciones/diplomados-impartidos` | `msperfil/diplomados` | **msperfil** |
| `trabajos_titulacion` | `msaportaciones/trabajos-titulacion` | `msperfil/tesis` | **msperfil** |
| `estancias_investigacion` | `msaportaciones/estancias-investigacion` | `msperfil/estancias` | **msperfil** ⚠ "Sección anterior" |

> ⚠️ `estancias_investigacion` is now labelled "Sección anterior" in the UI — platform may have deprecated it.
> ⚠️ `cursos_impartidos`, `diplomados_impartidos`, `trabajos_titulacion` moved to `msperfil` service.

### Scope — sections we touch

```
Trayectoria profesional
  ├── Producción / Científica-humanística    (11 subsections)
  │     articulos, libros, capitulos, reportes, informes,
  │     dossier-o-numero-tematico, antologias, traducciones,
  │     prologos-estudios-introductorios, curadurias, base-datos-primarios
  │
  ├── Aportaciones                           (12 subsections)
  │     desarrollos-tecnologicos-innovaciones, propiedades-intelectuales,
  │     transferencias-tecnologicas, informes-tecnicos,
  │     proyectos-investigacion, planes-estudio,
  │     colaboraciones-interinstitucionales, coordinaciones,
  │     jurados, evaluaciones-programas-proyectos,
  │     dictaminaciones-publicaciones, dictaminaciones-especializadas
  │
  ├── Fortalecimiento / Formación comunidad  (8 subsections)
  │     docencia: msperfil/cursos-impartidos, msperfil/diplomados,
  │               capacitaciones, talleres, seminarios, tutorias
  │     msperfil/tesis, participacion-editorial
  │
  ├── Estancias                              (1 subsection)
  │     msperfil/estancias  [labelled "Sección anterior" — check if deprecated]
  │
  └── Acceso universal al conocimiento       (4 subsections)
        medios-escritos, audiovisuales-radiofonicos-digitales,
        museografia-espacios-educacion-no-formal, eventos-comunicacion
```

### Sections we DO NOT touch
- Solicitud
- Compartir Mi Perfil Único
- Acerca de
- Educación (already complete)

---

## Evidence folder structure

```
evidence/
  produccion/cientifica-humanistica/
    articulos/          libros/             capitulos/
    reportes/           informes/           dossier-o-numero-tematico/
    antologias/         traducciones/       prologos-estudios-introductorios/
    curadurias/         base-datos-primarios/

  aportaciones/
    desarrollos-tecnologicos-innovaciones/  propiedades-intelectuales/
    transferencias-tecnologicas/            informes-tecnicos/
    proyectos-investigacion/                planes-estudio/
    colaboraciones-interinstitucionales/    coordinaciones/
    jurados/    evaluaciones-programas-proyectos/
    dictaminaciones-publicaciones/  dictaminaciones-especializadas/

  fortalecimiento/
    docencia/
      cursos-impartidos/  diplomados-impartidos/  capacitaciones/
      talleres/           seminarios/             tutorias/
    trabajos-titulacion/
    participacion-editorial/

  estancias/
    estancias-investigacion/    ← msperfil/estancias [labelled "Sección anterior"]

  acceso-universal/
    medios-escritos/                        audiovisuales-radiofonicos-digitales/
    museografia-espacios-educacion-no-formal/   eventos-comunicacion/
```

Each leaf folder contains:
- `NNN_slug.json` — metadata matching the section's schema
- `NNN_slug.pdf` — evidence document (optional for some sections)

---

## Tracking conventions

Every evidence JSON file has a `_meta` block:

```json
{
  "_status": "pending",
  "_rizoma_id": null,
  "_uploaded_at": null,
  "_notes": ""
}
```

Valid `_status` values:
- `"pending"` — not yet uploaded
- `"uploaded_meta"` — metadata saved, document not yet attached
- `"complete"` — metadata + document uploaded successfully
- `"already_exists"` — was in Rizoma before this project
- `"error"` — failed (see `_notes`)

---

## Project phases

| Phase | Script | Status | Output |
|-------|--------|--------|--------|
| 1 — Auth + API recon | `scripts/01_recon.py` | ✅ Complete | `logs/api_map.json` |
| 2 — Section/field mapping | `scripts/02_map_activities.py` | ✅ Complete | `config/schemas/*.json` |
| 3 — Local data entry | (manual) | ⬜ Not started | `evidence/**/*.json` |
| 4 — Upload automation | `scripts/03_upload.py` | ⬜ Not started | `logs/upload_log.json` |
| 5 — Tracking dashboard | `scripts/04_tracker.py` | ⬜ Not started | `logs/status_report.md` |

---

## Working rules for Claude

1. **Always work incrementally.** Complete and verify one phase before starting the next.
2. **Never assume field names.** Use `config/schemas/{slug}.json` — not memory or templates.
3. **Never use dropdown display strings.** Always fetch catalog IDs from `saci` before POSTing.
4. **Preserve existing data.** Before any write, check `_status`. Skip `"complete"` and `"already_exists"` unless explicitly told otherwise.
5. **Log everything.** Every API call result → `logs/upload_log.json` with timestamp + status code.
6. **Dry-run first.** All upload scripts default to `--dry-run`. Pass `--live` to actually write.
7. **Screenshot on error.** Any browser script saves a screenshot on failure.
8. **Ask before modifying schemas.** If a field mapping is ambiguous, ask rather than guess.
9. **Track status rigorously.** Update `_status` in JSON after every operation.
10. **Articulos already exist.** 11 records found — check before uploading to avoid duplicates.
11. **Regenerate the report after every change.** After any upload, edit, or status update run `python3 scripts/04_tracker.py --md` to keep `logs/status_report.md` current.

---

## Current state

- [x] Phase 1 complete — login works, base API mapped
- [x] Phase 2 complete — 36 sections mapped, all forms captured, evidence folders created
- [~] Phase 3 — populate `evidence/` JSON files with Mario's data (medios-escritos done; all others pending)
- [x] Phase 4 complete — upload scripts built and tested (`scripts/10_upload_blog.py`, `scripts/auth.py`)
- [x] Phase 5 complete — tracker dashboard (`scripts/04_tracker.py --md` → `logs/status_report.md`)

### Platform counts as of 2026-03-24
| Section | On platform |
|---------|:-----------:|
| Artículos | 11 |
| Libros | 1 |
| Capítulos | 7 |
| Talleres | 3 |
| Evaluaciones programas | 1 |
| Dictaminaciones especializadas | 2 |
| Cursos impartidos | 74 |
| Trabajos de titulación | 26 |
| Estancias de investigación | 1 |
| Medios escritos (Blog) | 94 ✅ |
| Audiovisuales/Radiofónicos | 2 |
| All other 25 sections | 0 |

**Start here when resuming:** Phase 3 — create JSON evidence files for sections that have 0 on the platform. Use `config/schemas/{slug}.json` for field reference. Run `python3 scripts/04_tracker.py --md` after any change.
