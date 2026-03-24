# Rizoma SNII — Automatización de evidencias

Herramientas en Python para gestionar el expediente del **Sistema Nacional de Investigadores (SNII)** en la plataforma [rizoma.conahcyt.mx](https://rizoma.conahcyt.mx).

El proyecto permite:
- Autenticarse automáticamente usando credenciales del `.env` (renovación automática de sesión)
- Mapear la estructura completa de las 36 secciones de la plataforma
- Registrar evidencias localmente como archivos JSON
- Subir registros al API de Rizoma de forma automatizada
- Generar un reporte de estado con lo que ya está en la plataforma vs. lo que falta

---

## Requisitos

- Python 3.10 o superior
- Playwright (para la autenticación con Keycloak/OAuth2)

```bash
pip3 install playwright --break-system-packages
python3 -m playwright install chromium
```

Opcional — solo si usas el script de filtrado con IA (`06_filter_blog.py`):
```bash
pip3 install anthropic --break-system-packages
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Configuración inicial

**1. Clona el repositorio**

```bash
git clone <url-del-repo>
cd SNII-2026
```

**2. Crea tu archivo `.env`**

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales de Rizoma y los datos de tu institución. El archivo tiene instrucciones detalladas sobre cómo encontrar cada valor.

> El archivo `.env` está en `.gitignore` — nunca se sube al repositorio.

**3. Verifica la autenticación**

```bash
python3 scripts/01_recon.py
```

Esto abre un navegador headless, inicia sesión en Rizoma vía Keycloak y guarda las cookies en `session/session_state.json`. Los demás scripts renuevan la sesión automáticamente cuando expira.

---

## Uso rápido

### Ver el reporte de estado

```bash
python3 scripts/04_tracker.py --md
```

Muestra en terminal y guarda en `logs/status_report.md` el conteo de registros en la plataforma vs. tus archivos locales para las 36 secciones. Ejecuta este comando después de cualquier cambio.

### Subir entradas de blog (*Medios escritos*)

```bash
# Modo simulación — muestra lo que se enviaría sin escribir nada:
python3 scripts/10_upload_blog.py

# Prueba real con 1 entrada:
python3 scripts/10_upload_blog.py --live --limit 1

# Subir todo:
python3 scripts/10_upload_blog.py --live
```

---

## Scripts disponibles

| Script | Descripción |
|--------|-------------|
| `auth.py` | Módulo compartido de autenticación (importado por los demás) |
| `01_recon.py` | Autentica y mapea el API base |
| `02_map_activities.py` | Mapea todas las secciones y guarda esquemas en `config/schemas/` |
| `04_tracker.py` | Reporte de estado: plataforma vs. evidencias locales |
| `05_endpoint_check.py` | Re-valida endpoints tras actualizaciones de la plataforma |
| `06_filter_blog.py` | Filtra posts de Ghost export con Claude AI |
| `06_filter_blog_local.py` | Filtra posts de Ghost export de forma interactiva (sin API) |
| `10_upload_blog.py` | Sube entradas de blog a la sección *Medios escritos* |

---

## Estructura del proyecto

```
SNII-2026/
├── .env                    # Credenciales y configuración personal (gitignored)
├── .env.example            # Plantilla — copia esto como .env
├── config/
│   └── schemas/            # Esquemas JSON de cada sección (36 archivos)
├── evidence/               # Evidencias locales organizadas por sección
│   ├── produccion/cientifica-humanistica/
│   │   ├── articulos/
│   │   ├── libros/
│   │   └── ...
│   ├── aportaciones/
│   ├── fortalecimiento/
│   ├── estancias/
│   └── acceso-universal/
│       └── medios-escritos/
├── logs/                   # Logs de subida y reportes (gitignored)
│   └── status_report.md
├── raw_evidence/           # Datos crudos (exportaciones de Ghost, etc.)
├── scripts/                # Scripts de automatización
└── session/                # Cookies de sesión activa (gitignored)
```

---

## Formato de archivos de evidencia

Cada registro es un archivo JSON en la subcarpeta correspondiente de `evidence/`. El campo `_meta` lleva el estado:

```json
{
  "titulo": "...",
  "anio": 2024,
  "_meta": {
    "_status": "pending",
    "_rizoma_id": null,
    "_uploaded_at": null,
    "_notes": ""
  }
}
```

| `_status` | Significado |
|-----------|-------------|
| `pending` | Listo localmente, aún no subido |
| `uploaded_meta` | Metadatos subidos, sin documento adjunto |
| `complete` | Metadatos + documento subidos |
| `already_exists` | Existía en Rizoma antes de este proyecto |
| `error` | Falló el envío (ver `_notes`) |

---

## Cómo encontrar el ID de tu institución

El campo `INSTITUCION_ID` en `.env` es el identificador numérico de tu institución en el catálogo interno de Rizoma. Para encontrarlo:

1. Abre Rizoma en el navegador con DevTools (F12) → pestaña **Network**
2. Agrega cualquier registro en cualquier sección y selecciona tu institución
3. Busca la petición `POST` que se genera y revisa el cuerpo JSON
4. En el campo `"institucion"` encontrarás el objeto completo con el `"id"` numérico

Ejemplo:
```json
"institucion": {
  "id": 12345,
  "clave": "1234567",
  "nombre": "NOMBRE DE LA INSTITUCION",
  "entidad": {"clave": "XXX", "nombre": "Estado"},
  ...
}
```

---

## Arquitectura del API de Rizoma

La plataforma expone tres microservicios:

| Servicio | Ruta base | Contenido |
|----------|-----------|-----------|
| `msaportaciones` | `/services/msaportaciones/api/` | Registros de producción académica |
| `msperfil` | `/services/msperfil/api/` | Perfil, cursos, tesis, estancias |
| `saci` | `/services/saci/api/v1/` | Catálogos de opciones (dropdowns) |

**Notas importantes:**

- Los valores de campos tipo catálogo (tipo de publicación, audiencia, etc.) son objetos con `id` y `nombre`. Nunca envíes solo el texto — siempre usa el objeto completo del catálogo.
- La subida de registros con documento es en dos pasos: POST de metadatos → obtiene `id` → POST del archivo.
- El API acepta `size` máximo de 100 registros por petición.
- El certificado SSL de la plataforma es de gobierno y falla la validación estándar; los scripts lo desactivan con `ssl.CERT_NONE`.
- La autenticación es OAuth2 Authorization Code Flow vía Keycloak en `idm.conahcyt.mx`. La sesión se guarda localmente y se renueva automáticamente al expirar.

---

## Historial de cambios de la plataforma

La plataforma Rizoma se actualiza con frecuencia. Los cambios de endpoints detectados se documentan en `CLAUDE.md`. Si un script falla con 404, ejecuta `05_endpoint_check.py` para re-validar los endpoints.

---

## Contribuciones

Este proyecto fue desarrollado para gestionar el expediente SNII de un investigador en México, pero la lógica es reutilizable para cualquier usuario de Rizoma/CONAHCYT. Si lo adaptas o mejoras, eres bienvenido a contribuir.
