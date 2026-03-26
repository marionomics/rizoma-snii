"""
notion_classify.py
==================
Reclassifica los 230 items de la BD "Constancias" en Notion usando los
nombres de sección correctos de Rizoma, y agrega la propiedad "Notas Rizoma".

Usage:
  python3 scripts/notion_classify.py              # dry-run (default)
  python3 scripts/notion_classify.py --live       # aplica cambios reales
  python3 scripts/notion_classify.py --live --limit 5   # prueba con 5 items
"""

import json
import ssl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from auth import load_env

_env = load_env()
NOTION_TOKEN = _env.get("NOTION_TOKEN", "").strip()
if not NOTION_TOKEN:
    print("✗ NOTION_TOKEN no está configurado en .env")
    sys.exit(1)

DB_ID   = "718520e3-202f-420b-98c0-857901ff48bf"   # Constancias
DRY_RUN = "--live" not in sys.argv
LIMIT   = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

import urllib.request, urllib.error

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE

_HEADERS = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type":   "application/json",
}


def notion_req(method, path, body=None, retries=3):
    url  = f"https://api.notion.com/v1/{path}"
    data = json.dumps(body).encode() if body else None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=_HEADERS, method=method)
            with urllib.request.urlopen(req, context=_CTX, timeout=25) as r:
                raw = r.read().decode(errors="replace")
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            return e.code, {"error": raw[:600]}
        except (TimeoutError, OSError, Exception) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)   # backoff: 1s, 2s, 4s
            else:
                return 0, {"error": f"Timeout/network after {retries} attempts: {e}"}


def add_notas_property():
    status, db = notion_req("GET", f"databases/{DB_ID}")
    if status != 200:
        print(f"  ✗ No se pudo obtener la BD: {db}")
        return False
    if "Notas Rizoma" in db.get("properties", {}) or "Notas Rizoma" in db.get("properties", {}):
        print("  ✓ Propiedad 'Notas Rizoma' ya existe")
        return True
    if DRY_RUN:
        print("  [DRY RUN] Agregaría propiedad 'Notas Rizoma' (rich_text)")
        return True
    status, resp = notion_req("PATCH", f"databases/{DB_ID}",
                              {"properties": {"Notas Rizoma": {"rich_text": {}}}})
    if status == 200:
        print("  ✓ Propiedad 'Notas Rizoma' agregada")
        return True
    print(f"  ✗ Error al agregar propiedad: {resp}")
    return False


def update_page(page_id, section, note):
    props = {
        "Tipo de Producto Rizoma": {
            "select": {"name": section} if section else None
        },
        "Notas Rizoma": {
            "rich_text": [{"type": "text", "text": {"content": note[:2000]}}]
        } if note else {"rich_text": []},
    }
    if DRY_RUN:
        return 200, {}
    return notion_req("PATCH", f"pages/{page_id}", {"properties": props})


# ── Mapping: page_id → (sección Rizoma, nota descriptiva) ────────────────────
MAPPING = {
    "005bb3fa-f028-4219-aa10-fe5ea55cb2a7": ("No se va a usar", "Reporte de evaluación de materia (Microeconomía II, 2021). No aplica como producto SNII."),
    "00a6c2a2-c033-47f2-bdb4-721c9b9cbb3d": ("Trabajos de titulación", "Acta de examen de titulación de Alexis Chávez. Participación como jurado/asesor."),
    "01ca8883-1f4e-4071-a636-725c4b54d7b6": ("Cursos impartidos", "Constancia de impartición del curso Portafolios de Inversión."),
    "03a5ff92-b11b-4495-81fe-bb3b9d36d36b": ("Dictaminaciones de publicaciones", "Constancia de arbitraje para la revista ETyP (Economía, Teoría y Práctica)."),
    "06306105-5313-42d1-8d23-467e6806974e": ("Trabajos de titulación", "Constancia de asesoría de tesis de Leonardo."),
    "0a65316e-eae5-4307-bd74-13b807279257": ("Eventos de comunicación", "Participación como comentarista en Coloquio de Estadística Aplicada."),
    "0ae9a393-33d0-42e2-9728-9e8a694f0c60": ("Evaluaciones de programas y proyectos", "Constancia de evaluador del Sistema Nacional de Investigadores (SNI) 2022."),
    "0b3152dd-6468-4621-ab2c-3be862afbe93": ("Colaboraciones interinstitucionales", "Participación en actividades del GIECAE (Grupo de Investigación en Economía y Ciencias Administrativas Especializadas) 2021-B."),
    "13f729b5-983f-8028-8db0-ef908d0d1d73": ("Coordinaciones", "Participación en reunión del claustro académico. Actividad de gestión institucional."),
    "13f729b5-983f-8083-813c-c3836e8c2a4c": ("Eventos de comunicación", "Participación en coloquio académico como ponente o comentarista."),
    "13f729b5-983f-80a5-9056-c19dd44bb905": ("Trabajos de titulación", "Constancia como evaluador del trabajo de titulación de Jesús Alberto Rodríguez."),
    "13f729b5-983f-80b3-aed8-d97f34a52d50": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Oscar Daniel."),
    "13f729b5-983f-80e2-960c-f8daea180c75": ("No se va a usar", "Constancia de asistencia a coloquio (2024). Solo asistencia, no participación activa."),
    "14b729b5-983f-8075-be71-e1fcfd674053": ("Seminarios", "Participación en seminario sobre pobreza. Actividad de formación/difusión académica."),
    "159729b5-983f-80a4-b437-d00452c9f805": ("No se va a usar", "Constancia de año sabático. No aplica directamente como producto SNII."),
    "1813a007-ee16-45d0-8e13-f652a9a4a9f5": ("Tutorías", "Constancia de actividad de tutoría académica, DGO 2021."),
    "181f8409-b5cc-47ec-8040-8e6edc29d2b5": ("Eventos de comunicación", "Participación en coloquio académico como ponente o comentarista."),
    "182729b5-983f-801c-8912-cc993a355098": ("No se va a usar", "Evaluación de materia Análisis de Datos para Mercadotecnia. No aplica como producto SNII."),
    "182729b5-983f-8025-998f-db3454eb9177": ("Eventos de comunicación", "Constancia de ponencia presentada en Lumen Index. Presentación en congreso/evento académico."),
    "182729b5-983f-8038-90f6-e7ffa5a17be3": ("Dictaminaciones de publicaciones", "Constancia de arbitraje de capítulo de libro. Evaluación científica de publicación académica."),
    "182729b5-983f-8051-a329-e8acdba807fe": ("No se va a usar", "Evaluación de materia Portafolios de Inversión. No aplica como producto SNII."),
    "182729b5-983f-8096-b90c-dc2034b8117e": ("No se va a usar", "Evaluación de materia Investigación de Operaciones. No aplica como producto SNII."),
    "182729b5-983f-809a-9230-d3eda092d8e3": ("No se va a usar", "Evaluación de materia Economía Empresarial. No aplica como producto SNII."),
    "182729b5-983f-80a6-9cf3-e1684a3a7a40": ("Tutorías", "Constancia de tutorías académicas 2024."),
    "182729b5-983f-80e4-a8d7-dda02d3f7429": ("No se va a usar", "Evaluación de materia Microeconomía Aplicada. No aplica como producto SNII."),
    "183729b5-983f-803f-8ed6-cc639e888105": ("Proyectos de investigación", "Proyecto de investigación sobre energía. Evidencia de participación en proyecto."),
    "183729b5-983f-8055-9870-fa02a3959027": ("Proyectos de investigación", "Proyecto de investigación Yucatán. Evidencia de participación en proyecto de investigación."),
    "183729b5-983f-80ba-9c22-deba7c080684": ("Talleres", "Constancia de impartición de taller de econometría."),
    "183729b5-983f-80d4-a93e-cafe1cc5d8f7": ("Colaboraciones interinstitucionales", "Constancia de actividades en el GIECAE (Grupo de Investigación en Economía y Ciencias Administrativas Especializadas)."),
    "184729b5-983f-8033-bc69-e5ae4e8cb7ad": ("No se va a usar", "Constancia de servicio social. No aplica como producto SNII."),
    "186729b5-983f-8003-8689-f060258644aa": ("Cursos impartidos", "Constancia de impartición de clases. Evidencia de docencia."),
    "1900d8c1-04b0-4990-aae5-3a7f6b6bb602": ("Dictaminaciones de publicaciones", "Constancia de dictaminación/arbitraje para Korpus 21 (revista académica)."),
    "19e729b5-983f-8085-a98c-eeafabcfe88f": ("Trabajos de titulación", "Acta de examen de titulación de Mariana. Participación como jurado."),
    "19f7829e-d85e-461d-b96d-308dbeee582b": ("Planes de estudio", "Constancia de elaboración de Unidad de Aprendizaje para Mercados Financieros (MGN)."),
    "1aa729b5-983f-8122-89d6-cc235c53a890": ("Evaluaciones de programas y proyectos", "Participación como integrante del Panel Consultivo del INEVAP."),
    "1d4aaa7f-8fb4-41ce-abd7-dc641a69ab0f": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Oscar Daniel."),
    "1f7729b5-983f-801f-a57c-d03a428e4e9b": ("No se va a usar", "Diplomado en Investigación Jurídica (tomado como alumno, no impartido)."),
    "1f7729b5-983f-8040-8fdd-d8c2af6baca6": ("No se va a usar", "Diplomado en Teoría del Delito (tomado como alumno, no impartido)."),
    "202729b5-983f-800f-b46a-dd5b0be25726": ("Trabajos de titulación", "Acta de examen profesional de Eduardo Castro López. Participación como jurado."),
    "202729b5-983f-8014-af6d-f96edbe61d84": ("Trabajos de titulación", "Acta de examen profesional de Carmen de María Flores. Participación como jurado."),
    "206729b5-983f-80d4-a41d-c3c461c17b0a": ("Talleres", "Constancia de participación/organización en el Reto Banxico 2025. Taller de divulgación sobre política monetaria para universitarios."),
    "217729b5-983f-8005-a50b-ec0858b9458d": ("Evaluaciones de programas y proyectos", "Constancia como evaluador de Proyecto de Ciencia de Frontera (CONAHCYT)."),
    "217729b5-983f-802c-83fa-d1ac010d2a11": ("No se va a usar", "Publicación CENID. Sin archivo adjunto; pendiente de verificar."),
    "21965e67-801f-435c-bdfe-2a0c2f6001de": ("Trabajos de titulación", "Constancia de asesoría de tesis de Cinthia Avilés."),
    "219729b5-983f-8078-87cc-e8125f7e5478": ("Evaluaciones de programas y proyectos", "Constancia como evaluador de estancia posdoctoral (CONAHCYT/SNI)."),
    "21d9be88-1c92-4a2d-82d0-7c1cf6997fd3": ("Trabajos de titulación", "Constancia de dirección de tesis de Samantha."),
    "220444d3-f287-4125-9ac3-9def60ac6e31": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Estefanía."),
    "227729b5-983f-8032-a393-e8f4a00da901": ("No se va a usar", "Constancia de asistencia a coloquio DGO. Solo asistencia, sin participación activa."),
    "227729b5-983f-808a-8920-cd5682f6bf56": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Carola (DGO)."),
    "227729b5-983f-80b5-8720-ee55cd8bfc97": ("Trabajos de titulación", "Constancia como evaluador de avance de tesis de Estefanía Valadez."),
    "227729b5-983f-80c1-9d3a-d4d879b2fcfc": ("Evaluaciones de programas y proyectos", "Constancia como integrante de comisión evaluadora de proceso de selección DGO."),
    "250729b5-983f-801b-b4b5-f5cca2a9fffc": ("No se va a usar", "Constancia de semana de inducción. No aplica como producto SNII."),
    "250729b5-983f-8021-a76f-f35934e0ce36": ("Trabajos de titulación", "Constancia como integrante de comité de evaluación para Torres. Participación en jurado."),
    "250729b5-983f-80fe-9127-d90578e8e492": ("Coordinaciones", "Constancia como Jefe de Carrera de LENI (Lic. en Economía e Negocios Internacionales)."),
    "27b15b22-e2db-4111-8f9b-6218c17fd49b": ("Trabajos de titulación", "Constancia de dirección de tesis (2020)."),
    "290729b5-983f-80db-822c-e021de54db2d": ("Eventos de comunicación", "Conferencia Magistral sobre Crecimiento Sostenible y Transformación Digital (o afín). Evento académico."),
    "292729b5-983f-8005-9347-e14ed6a074a2": ("Trabajos de titulación", "Constancia como evaluador del DIIE (División de Investigación e Innovación Empresarial)."),
    "292729b5-983f-8075-89e3-fdf0d5e09c5f": ("Eventos de comunicación", "Conferencia sobre Teoría de Juegos impartida en evento académico."),
    "292729b5-983f-80d1-90e8-e0f233c3ec1e": ("Dictaminaciones de publicaciones", "Constancia de dictaminación del libro sobre Finanzas (Universidad de Colima)."),
    "295729b5-983f-802f-a90f-e0dacd2df23c": ("Dictaminaciones de publicaciones", "Constancia de dictaminación de libro (BUAP — Benemérita Universidad Autónoma de Puebla)."),
    "29f729b5-983f-8064-8b13-c1bb1ae0d57e": ("Diplomados impartidos", "Constancia de participación como ponente en diplomado académico."),
    "29f729b5-983f-806a-8283-c5328c10611f": ("Eventos de comunicación", "Constancia de participación como panelista en foro/evento sobre Mundo Laboral."),
    "2a3361c6-774b-4fb5-9ff4-ada7b4241fe7": ("Planes de estudio", "Constancia como integrante de Comisión Curricular. Participación en diseño/revisión de planes de estudio."),
    "2acb7883-1691-4159-b4a8-560df96bc140": ("Cursos impartidos", "Constancia de impartición de clase de Economía Empresarial."),
    "2aec4569-af66-453b-8e18-3bb535cbcd6d": ("Trabajos de titulación", "Tesis de Mariana Saravia. Participación como director/asesor de tesis."),
    "2b960f9f-e7b4-44b0-9b5a-35711021b263": ("Coordinaciones", "Participación como Miembro del Consejo Técnico A 2022. Actividad de gestión académica."),
    "2bdc4cc1-b16d-42b2-a836-9af152c56298": ("Dictaminaciones de publicaciones", "Constancia de arbitraje en CIIE. Revisión de ponencias para congreso internacional."),
    "2c51b873-00f5-48e9-a473-ebc0e3371df5": ("Evaluaciones de programas y proyectos", "Constancia de participación en entrevistas del DEP (Departamento de Estudios de Posgrado) 2022. Comité de admisión."),
    "2e2729b5-983f-807a-b930-f275cba9539b": ("No se va a usar", "Diplomado en Derecho de Obligaciones y Contratos (tomado como alumno, no impartido)."),
    "2ee729b5-983f-8050-a2a9-d4810df8f39d": ("No se va a usar", "Sin título ni archivo. Entrada vacía."),
    "2f0729b5-983f-801c-add2-e7942b332338": ("Trabajos de titulación", "Acta/constancia de examen de Mario Peyro. Participación como jurado de examen profesional."),
    "2f0729b5-983f-802f-92ed-cbc1be9937e8": ("Dictaminaciones de publicaciones", "Constancia como revisor de ponencia. Dictaminación de trabajo académico para congreso/evento."),
    "2f0729b5-983f-8043-be04-f80ef6671027": ("Trabajos de titulación", "Constancia de asesoría de tesis."),
    "2f0729b5-983f-8049-9003-cb998261d262": ("Eventos de comunicación", "Asesoría de ponencias en CICEA. Participación activa en congreso de economía y administración."),
    "2f0729b5-983f-8072-8d0b-df87eb5eeafb": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Estefanía Valadez."),
    "2f0729b5-983f-809f-8fcc-c349fbf68d88": ("Trabajos de titulación", "Constancia como evaluador del protocolo de tesis de Víctor."),
    "2f0729b5-983f-80ad-aefb-da9eade72482": ("Talleres", "Constancia de impartición de taller en el marco del Reto Banxico. Divulgación de política monetaria para estudiantes."),
    "2f0729b5-983f-80c4-896f-f3ed46df9e71": ("Trabajos de titulación", "Acta de examen profesional de Diana. Participación como jurado."),
    "2f0729b5-983f-80d3-8bf7-ef13f428749c": ("No se va a usar", "Reto Banxico (edición anterior). Clasificado como no relevante para SNII en revisión previa."),
    "2f0729b5-983f-80d9-a511-e416de25bf2f": ("Trabajos de titulación", "Acta de examen profesional de Astrid. Participación como jurado."),
    "2f0729b5-983f-80e9-b34e-ef839eaf0ab0": ("Coordinaciones", "Constancia de participación en claustro académico. Actividad de gestión institucional."),
    "2f0729b5-983f-80ea-93cc-db6dd33fdfc7": ("Trabajos de titulación", "Constancia de asesoría/dirección de tesis de Daniela Fernanda Quintana Ortega."),
    "2f0729b5-983f-80f0-8078-fa6b57cbcb1c": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Carola."),
    "2f0729b5-983f-80f7-a94b-dc8886a8daf6": ("Jurados", "Constancia como jurado en examen de Alan Rangel. Evaluación de trabajo académico."),
    "2f1729b5-983f-806b-8c8d-d341be23d6ef": ("Trabajos de titulación", "Acta de examen profesional de Carmen Flores Romero. Participación como jurado."),
    "2f1729b5-983f-8097-96d1-d9a3523c4d3a": ("Trabajos de titulación", "Acta de examen profesional de Dayanna Verdín. Participación como jurado."),
    "2f1729b5-983f-80b0-becb-e0b41f95e7ab": ("Trabajos de titulación", "Acta de examen profesional de Vanessa Barboza. Participación como jurado."),
    "2f1729b5-983f-80b4-aa18-cb531bd1c6f4": ("Trabajos de titulación", "Acta de examen profesional de Angélica Gurrola. Participación como jurado."),
    "2f1729b5-983f-80bf-ba4a-d44113ceda5b": ("Trabajos de titulación", "Acta de examen profesional de Eduardo Castro. Participación como jurado."),
    "2f4729b5-983f-8035-b883-e698e1d6937c": ("No se va a usar", "Constancia de servicio social. No aplica como producto SNII."),
    "2f4729b5-983f-8043-a66a-deff9e232b73": ("Jurados", "Constancia de participación como jurado en Debate Académico."),
    "2f4729b5-983f-8053-b5f8-e8b041752953": ("Eventos de comunicación", "Conferencia/charla '4 formas de usar datos en tu modelo de negocio'. Divulgación de economía aplicada."),
    "2f4729b5-983f-805d-bdee-d108b2839706": ("Eventos de comunicación", "Conferencia sobre Inteligencia Artificial. Divulgación científica/tecnológica."),
    "2f4729b5-983f-8063-af3f-d80c9e63e3e1": ("Tutorías", "Constancia de tutorías académicas ciclo B 2025."),
    "2f4729b5-983f-8090-8f31-d8767e0029a5": ("Coordinaciones", "Constancia como Jefe de Carrera. Cargo de coordinación académica institucional."),
    "2f4729b5-983f-80c5-8fbf-cbaaac85e951": ("Eventos de comunicación", "Conferencia Magistral sobre razones económicas. Presentación académica en congreso/evento."),
    "2f5729b5-983f-80c0-8d49-cf5dab5f2b00": ("No se va a usar", "Sin título ni archivo. Entrada vacía."),
    "2fa729b5-983f-8006-9742-ffde7b63f3fb": ("Eventos de comunicación", "Entrevista de radio en el programa EmprendeT sobre Inteligencia Artificial. Sin archivo adjunto."),
    "2fa729b5-983f-80d8-bf86-d6656c926824": ("Tutorías", "Constancia de tutorías académicas ciclo A 2025."),
    "2fb99c99-b896-4a94-9a1d-e02c0ef5c046": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Alejandro."),
    "2fc1add5-1325-4fa9-bdf8-2388c63a5915": ("Cursos impartidos", "Constancia de impartición del curso Análisis Multivariado."),
    "2fc561a7-9763-4744-b76f-a597b577026a": ("Trabajos de titulación", "Acta de examen de grado de Jaqueline Fernández. Participación como jurado."),
    "2fc729b5-983f-8080-9328-fa97007f9d68": ("Dictaminaciones de publicaciones", "Constancia como revisor de ponencia en congreso académico."),
    "3069a8ea-735f-424e-a8bd-7e16bb7ebd6e": ("Trabajos de titulación", "Acta de examen profesional de Ivett Alejandra Saldaña. Participación como jurado."),
    "309729b5-983f-800f-ba88-d85d394bb48a": ("Trabajos de titulación", "Constancia de participación en trabajos de titulación (sin título en la base de datos)."),
    "309729b5-983f-8024-8596-f1b833832d95": ("Trabajos de titulación", "Constancia de participación en trabajos de titulación (sin título en la base de datos)."),
    "30b729b5-983f-8060-8f66-d0676b16dfa5": ("Evaluaciones de programas y proyectos", "Constancia como Integrante del Panel Consultivo del INEVAP 2024-2026."),
    "30b729b5-983f-807f-a153-c009050a3e97": ("Eventos de comunicación", "Entrevista de radio sobre econometría. Divulgación científica en medios de comunicación."),
    "30b729b5-983f-80d0-adf7-ebd13411ad45": ("Talleres", "Constancia de impartición de taller sobre Inteligencia Artificial."),
    "311729b5-983f-8069-aa8e-e495b23ca813": ("Trabajos de titulación", "Constancia de dirección de tesis de Noé."),
    "319729b5-983f-800f-ab37-fef4802a8ea7": ("Cursos impartidos", "Constancia de impartición del curso Cálculo Estocástico (2019-B)."),
    "319729b5-983f-802b-a1f8-e690049d27bc": ("Cursos impartidos", "Constancia de impartición del curso Cálculo Estocástico (2019-B). Posible duplicado."),
    "319729b5-983f-8053-97a0-dd96705c1c2f": ("No se va a usar", "Sin título ni archivo. Constancia de clase sin datos."),
    "319729b5-983f-8078-ba83-dcfd3fbd818a": ("Cursos impartidos", "Constancia de impartición del curso Simulación Estadística (2016-B)."),
    "31a5d4c6-a366-4244-93d4-0f065f5eb850": ("Coordinaciones", "Participación como Miembro del NAB (National Advisory Board) DGO 2020. Actividad de vinculación institucional."),
    "31f729b5-983f-8083-8685-c5743d07a715": ("No se va a usar", "Sin título ni archivo. Constancia de clase sin datos."),
    "32684f37-0d37-4c4b-998a-edb1b76dc956": ("Evaluaciones de programas y proyectos", "Constancia como evaluador de fondo CONAHCYT. Dictaminación de proyectos de investigación."),
    "34ad376c-8a9e-4153-9472-bcb2c31ba6eb": ("Tutorías", "Constancia de actividad de tutoría académica, DGO 2020-A."),
    "356f4873-8bdd-44cb-8a5e-33c863697a92": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Genaro."),
    "36a1f246-ef11-46f2-a262-a9adf7b1cf23": ("Tutorías", "Constancia de tutorías académicas 2021."),
    "36c04d65-2689-47cf-89d4-1d2766d941c5": ("Eventos de comunicación", "Constancia de ponencia presentada en CIAACEA (Congreso Internacional de Administración, Contaduría y Ciencias Económico-Administrativas)."),
    "37cda6c5-d7a9-42b0-85c1-c842011db05a": ("No se va a usar", "Reconocimiento SNI UJED. Distinción institucional, no aplica como producto SNII."),
    "38499bb5-0b52-4816-b0a9-a37ee448049c": ("Proyectos de investigación", "Constancia de participación en proyecto de investigación sobre IED (Inversión Extranjera Directa), Exportaciones y Super Riqueza."),
    "38c18ff1-72d6-4b69-8ba4-cc5fcaa14888": ("Evaluaciones de programas y proyectos", "Constancia como integrante de la Red de Competitividad y Desarrollo Regional. Evaluación de programa/red de investigación."),
    "3a6eab59-c4d3-4bfd-8289-08b4fe891571": ("Planes de estudio", "Constancia como Coordinador de Comisión Curricular del ME (Maestría en Economía). Diseño/revisión de plan de estudios."),
    "3be6fa2f-6cfe-437d-bc4d-1521aa86e18b": ("No se va a usar", "Prácticas de Oveth. Supervisión de prácticas profesionales, no aplica como producto SNII."),
    "3da9a25c-4728-4739-b59c-dee54ea80b30": ("Colaboraciones interinstitucionales", "Constancia de participación en GIECAE: Difusión, Consultoría e Investigación. Grupo de investigación interinstitucional."),
    "3ea6e1df-d143-41a8-8084-3336c38d33cf": ("Cursos impartidos", "Constancia de impartición del curso Economía Empresarial."),
    "3f9ce6c2-2e94-4b43-98c7-bafb40902259": ("Trabajos de titulación", "Constancia como jurado en exámenes profesionales (varios)."),
    "4090ffc9-c05d-40ad-a104-ffd320f43491": ("Eventos de comunicación", "Conferencia sobre Mercadotecnia Digital con uso de Business Intelligence/Big Data."),
    "420f7114-ba93-4b15-b8f0-6bf940edbb86": ("Trabajos de titulación", "Constancia de dirección/asesoría de tesis de Oscar Daniel Olvera."),
    "43d3571a-9539-4909-871d-f9c299d1259a": ("Evaluaciones de programas y proyectos", "Constancia como evaluador en Flacso Encuesta Electoral (proyecto de investigación/evaluación)."),
    "43fc4c5e-fef4-4412-a8b5-0d1bd055dbde": ("Evaluaciones de programas y proyectos", "Constancia de participación en Comisión ESDEPED 2022 (Estímulos al Desempeño del Personal Docente)."),
    "46380a90-5777-40b8-ad8d-6490ae571a8c": ("Trabajos de titulación", "Constancia de dirección/asesoría de tesis de Moisés."),
    "466869a2-381d-4d81-aa52-2088cc810083": ("Colaboraciones interinstitucionales", "Constancia de participación en GIECAE (Grupo de Investigación en Economía y Ciencias Administrativas Especializadas)."),
    "4862ebfc-0abb-4127-8c23-a9c91ef8a4cd": ("Coordinaciones", "Constancia como Presidente de Academia A-2022. Cargo de coordinación y liderazgo académico."),
    "49cb6dd7-c0a9-4169-bf90-fdd838065f33": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Mario."),
    "4bd1f434-8a22-42e9-965d-776afb09e19a": ("Eventos de comunicación", "Constancia de participación en el 7o Coloquio de Investigación DEP FECA."),
    "4dbd6584-ecb7-4275-a4e4-6f2f4c91b49e": ("Tutorías", "Constancia de tutorías académicas ciclo B 2022."),
    "4e0f9fab-cf33-476e-be05-e2c11b0cf67d": ("Trabajos de titulación", "Acta de examen profesional de Carlos Alberto Escalier Flores. Participación como jurado."),
    "4e6e6284-f2ac-4997-8ff9-93d17edea9eb": ("Eventos de comunicación", "Constancia como relator en congreso académico."),
    "4e910967-14b8-47a6-b449-af22154801f7": ("Dictaminaciones de publicaciones", "Constancia como revisor en congreso académico. Evaluación de ponencias."),
    "4f2ea199-07d1-460e-9549-2bdfa94bac52": ("Evaluaciones de programas y proyectos", "Constancia de evaluación PNPC (Programa Nacional de Posgrados de Calidad, CONAHCYT)."),
    "50b43db6-0d22-49e0-8616-8e8c3d4c7261": ("Trabajos de titulación", "Acta de examen profesional de Brandon Alejandro Veloz Márquez. Participación como jurado."),
    "52f1b57f-123a-4ad6-9641-3884ab1e25ff": ("No se va a usar", "Constancia de asistencia a Foro de Clusters. Solo asistencia, no participación activa."),
    "55132e3d-fcf5-4738-a9ef-77f021d19ba2": ("Tutorías", "Constancia de tutoría académica 2021-A."),
    "558d4317-3b75-42e5-8977-a07a2b54b1cf": ("Talleres", "Constancia de impartición de Taller ENIGH (Encuesta Nacional de Ingresos y Gastos de los Hogares). Análisis de datos socioeconómicos."),
    "55f8bb62-f6cf-474d-8983-6c821fa9c54c": ("Trabajos de titulación", "Constancia de asesoría de tesis de Alexis."),
    "5863a9b6-afa3-4eb4-94a4-ef0b173f7a21": ("Eventos de comunicación", "Constancia como comentarista en coloquio de la Maestría en Estadística."),
    "5b3db066-134c-4715-800c-234b9e072b81": ("No se va a usar", "Sin título ni archivo. Entrada vacía."),
    "5cc5d9f8-b255-4dbf-a7fc-308b152459c1": ("Trabajos de titulación", "Acta de examen de Sandra Cordero. Participación como jurado."),
    "5d0cc658-b2ea-473e-ab00-9119b4f3ac1c": ("Evaluaciones de programas y proyectos", "Constancia como integrante de Comité Evaluador CACECA (Consejo de Acreditación en Ciencias Administrativas, Contables y Afines)."),
    "5d297256-7f5b-42e1-af1b-ee13e1bd12db": ("Cursos impartidos", "Constancia de impartición de materias 2022. Evidencia de docencia."),
    "5f3cecc0-21db-473f-8e9f-a669466d07ad": ("Tutorías", "Constancia de tutorías MAEA 2021-A (Maestría en Administración de Empresas Agropecuarias)."),
    "6189195d-752e-4f54-83b4-f7308966bb1e": ("Evaluaciones de programas y proyectos", "Constancia como entrevistador en proceso de admisión ciclo A-2022. Evaluación de aspirantes."),
    "61f70f70-c584-4873-b830-4f16523c9364": ("Evaluaciones de programas y proyectos", "Constancia como evaluador PRODEP (Programa para el Desarrollo Profesional Docente)."),
    "63d595a1-4212-44f5-98a0-7c58e7dbece1": ("Trabajos de titulación", "Constancia de asesoría de tesis de Xóchitl."),
    "684eb8d5-e1dd-4a56-93e4-a543547de599": ("Planes de estudio", "Constancia de revisión de Unidades de Aprendizaje. Participación en actualización curricular."),
    "69c4c96a-bfa5-4b5f-94c8-274170ec0fd2": ("Planes de estudio", "Constancia de participación en Comisión Curricular MGN. Diseño/revisión de plan de estudios."),
    "6b1e4f1e-7775-42e7-940c-d11fb44777d1": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Rodríguez Veloz, DGO 2022-B."),
    "6bdd752a-1a0c-4e19-94c0-a17e7416316d": ("Evaluaciones de programas y proyectos", "Constancia como evaluador del Sistema Nacional de Investigadores (SNI) 2022."),
    "712523e7-ff34-4880-94af-73c5d4701e22": ("Eventos de comunicación", "Constancia de participación en Congreso de Egresados DGO. Presentación/ponencia."),
    "72bb9abc-704e-4c6e-a078-c711965724cb": ("No se va a usar", "Diplomado en Derecho Financiero (tomado como alumno, no impartido)."),
    "730a85d5-3cdd-4c00-a3f3-13ae98e6694a": ("Trabajos de titulación", "Constancia como vocal en examen de titulación de Karla Mariana."),
    "732bfb72-99e4-47b4-a521-9e7bde76184f": ("Eventos de comunicación", "Conferencia sobre Tendencias de Consumo en las Empresas. Participación en evento académico/empresarial."),
    "733873b1-4ee9-4194-9b7e-0e6418cc4995": ("Planes de estudio", "Constancia de elaboración de Unidad de Aprendizaje de Economía Empresarial. Diseño curricular."),
    "73836c1f-7618-4187-ae40-5528c4ce56f3": ("Cursos impartidos", "Constancia de impartición de clases 2020, DEP-FECA (Departamento de Estudios de Posgrado, FECA)."),
    "764e7dcc-ccce-44c9-ad5a-83f0c6f4d1ab": ("Trabajos de titulación", "Acta de examen profesional de Carolina González Macías. Participación como jurado."),
    "7d859cb5-2719-4ec6-9e6f-9a90e63f053d": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Alejandro Morales."),
    "7dec14c1-e62e-4d1b-9530-0b216ecc713a": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Oscar H. (DGO)."),
    "803b58de-247f-453a-bc73-0805dc6dddc4": ("No se va a usar", "Reconocimiento SNI Cocyted. Distinción institucional, no aplica como producto SNII."),
    "806767aa-636b-4d87-97a2-de7d1350f898": ("Evaluaciones de programas y proyectos", "Constancia de participación en evaluación CIEES (Comités Interinstitucionales para la Evaluación de la Educación Superior)."),
    "84fa2923-eca2-4423-b179-16104a12007c": ("Coordinaciones", "Constancia de participación en Academia de Economía. Actividad de coordinación académica colegiada."),
    "86385bb1-906b-40e5-aea5-1ffa87f34c1d": ("No se va a usar", "Reporte de evaluación escolar A 2021. No aplica como producto SNII."),
    "86ca5f05-6667-4d5e-9fac-e71857216feb": ("Tutorías", "Constancia de tutoría MAEA 2021-B (Maestría en Administración de Empresas Agropecuarias)."),
    "86d60811-8013-43cb-9e1f-6b4ae0d15753": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Chely."),
    "880f2646-32a0-49b7-917d-23d174c2cf29": ("No se va a usar", "IMEF U. Sin archivo adjunto; pendiente de verificar o no aplica."),
    "890b558f-f52f-4864-9094-1f7c957b0dfe": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Carola Ramos."),
    "8a6f830e-aa64-4eb7-897f-5fc29c2c75d4": ("Eventos de comunicación", "Constancia de participación en International Finance Conference. Presentación en congreso internacional."),
    "8ac3cd1f-2131-4ddf-bf2e-2bffa3fded9e": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Oscar Olvera."),
    "8e7129ae-4de5-42d9-895f-ba0423b49e79": ("Seminarios", "Constancia de participación en Seminario GIECAE. Actividad académica del grupo de investigación."),
    "8fe380d5-4773-420a-a5ad-3cfcbf7cee82": ("Evaluaciones de programas y proyectos", "Constancia como integrante de Comité CACECA CP (Contaduría Pública). Evaluación de programa para acreditación."),
    "90f97425-d9fe-4977-937d-f6c2d580ce4e": ("Trabajos de titulación", "Constancia de asesoría de tesis de Oscar."),
    "94b44be1-ca26-4edf-b26f-979bb012ac01": ("Talleres", "Constancia de participación en Reto Banxico 2021. Taller de divulgación sobre política monetaria para universitarios."),
    "96ae06a1-45b3-4fd5-a4a3-6539566c3d31": ("Coordinaciones", "Constancia de participación en Reunión NAB A2021 (National Advisory Board). Vinculación institucional internacional."),
    "999b7817-e680-44c5-a405-b0f54004e92f": ("Coordinaciones", "Constancia de participación en Claustro Académico DGO. Actividad de gestión institucional."),
    "9f771776-fa65-4700-8284-3c93380ac646": ("Evaluaciones de programas y proyectos", "Constancia de participación en Comisión de Admisión. Evaluación de aspirantes a programas académicos."),
    "a0d13a16-7ff0-4da6-9b64-d01b2f331b1e": ("Coordinaciones", "Constancia de participación en Consejo Consultivo. Actividad de asesoría y vinculación institucional."),
    "a24b388f-fbdc-4506-8a7a-70704bf7cae8": ("Trabajos de titulación", "Constancia de dirección de tesis de Abraham."),
    "a300d061-0fe4-4e8a-8315-a8843d6182d6": ("Cursos impartidos", "Constancia de impartición del Curso de Metodologías para Procesos de Consultoría e Investigación."),
    "a4c51253-d6df-46d6-ae78-aa46eda74a79": ("Diplomados impartidos", "Constancia de participación como tutor/ponente en Diplomado de Investigación. Impartición de módulo académico."),
    "a4df1e45-31ab-4ce5-8b57-202a04bb83ef": ("No se va a usar", "Servicio Social de Gabriela Martos. Supervisión de servicio social, no aplica como producto SNII."),
    "a5d280a2-3c6f-4bb1-b491-d99faa85f364": ("Eventos de comunicación", "Constancia como Coordinador de Mesa en Congreso de Egresados DGO. Participación activa en congreso."),
    "a8b071d1-15a7-4845-946c-d6d996e5ac45": ("Trabajos de titulación", "Acta de examen de Oscar Gerardo Moreno García. Participación como jurado."),
    "aa94e0bc-783b-4f4a-8c2e-fe4d2143cec0": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Carlos 2021-B."),
    "ad11f48f-5c4b-4a91-bacd-1860acc2bf1f": ("Coordinaciones", "Constancia de participación en Academia de Economía. Actividad de coordinación académica colegiada."),
    "afea62fd-69da-4128-a730-94940d402182": ("Trabajos de titulación", "Constancia de asesoría de tesis de Paola."),
    "b2e26a6a-841b-4f6a-ab97-0aeb918c6325": ("Evaluaciones de programas y proyectos", "Constancia de participación en Comisión ESDEPED 2022. Evaluación del desempeño docente."),
    "b3205c7b-6afd-4b43-bd1e-42211fa4bbc3": ("No se va a usar", "Evaluación de portafolio A-2021. No aplica como producto SNII."),
    "b4b434bf-6f07-401a-bdd1-e7b53f528f9a": ("Trabajos de titulación", "Constancia de dirección/asesoría de tesis de Jesús Rodríguez."),
    "b6332870-115f-44ba-843d-3a2386622933": ("Trabajos de titulación", "Constancia como revisor de la intervención (tesis/proyecto) de Diana García Ruiz."),
    "b6be928f-7371-477e-87e6-57cd8d726bf7": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Samantha."),
    "b6e9ab40-07c9-49bd-9d94-58a97b04fb4b": ("Evaluaciones de programas y proyectos", "Constancia como integrante de Comité CACECA LA (Licenciatura en Administración). Evaluación de programa para acreditación."),
    "bae22de0-0564-4016-90c0-95726d7371d8": ("Trabajos de titulación", "Constancia como vocal en examen de tesis de Luis Lorenzo Romero."),
    "baf9d869-ed18-4703-90db-838f29e8704c": ("Trabajos de titulación", "Constancia como comentarista en tesis MAEA 2022 (Maestría en Administración de Empresas Agropecuarias)."),
    "be67775c-fb9d-40a0-9cf2-639723209f3e": ("Trabajos de titulación", "Acta de examen profesional de Gisell Alejandra Rivas Luna. Participación como jurado."),
    "c13f80f9-4bec-49ba-8121-8de11b586a28": ("Tutorías", "Constancia de tutorías académicas 2022-A."),
    "c25d3f00-8c93-41e6-83ac-78a4ac5518c2": ("Planes de estudio", "Constancia de elaboración de Unidad de Aprendizaje (UdA). Diseño curricular."),
    "c2cda703-835f-4329-a018-127f6062f26c": ("Dictaminaciones de publicaciones", "Constancia de evaluación de capítulo de libro sobre deuda. Arbitraje de publicación académica."),
    "c5ef1023-ca99-4536-a817-919337ceb948": ("No se va a usar", "Evaluación APPEE A-2021 (Apreciación Personal del Personal Académico). No aplica como producto SNII."),
    "c743bc00-6ae6-43d5-938f-f0112110d528": ("Trabajos de titulación", "Constancia de asesoría de tesis de Sabrina García Portillo."),
    "c9030a92-a8a3-4cb3-9712-3ea0a5486a2b": ("Evaluaciones de programas y proyectos", "Constancia como entrevistador en proceso de selección DGO 2021. Evaluación de aspirantes."),
    "cb7cb612-2666-4a52-b0a8-c3045c483af1": ("Trabajos de titulación", "Constancia de dirección/asesoría de tesis de Flor Gaucín."),
    "cd4836a2-ca1c-4336-9a84-3552e3178d8b": ("Evaluaciones de programas y proyectos", "Constancia de participación en ingreso CENEVAL 2021. Evaluación de examen nacional de ingreso a posgrado."),
    "d0308442-e462-4a23-b181-3f8b9dbfcb97": ("Trabajos de titulación", "Constancia de dirección/asesoría de tesis de Genaro."),
    "d43ce13c-9e37-466d-9447-cdfba5c7f294": ("Trabajos de titulación", "Constancia de asesoría de tesis de Fátima."),
    "d61f17f7-120f-44ab-8093-91c0074b81fd": ("Seminarios", "Constancia de participación en Seminario GIECAE (Grupo de Investigación en Economía y Ciencias Administrativas Especializadas)."),
    "d74f5b17-18bc-400e-a2e0-f4f3adbae8f7": ("Talleres", "Constancia de impartición del Taller de Exploración ENIGH: Economía del Hogar. Divulgación de análisis de datos socioeconómicos."),
    "d9a2116b-c69f-46b1-8b37-1abbfaad2839": ("Coordinaciones", "Constancia como Presidente de Academia A-2021 y B-2020. Cargo de liderazgo académico."),
    "d9a710ed-72fc-4d64-b1e3-c098510cef51": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Jesús Alberto."),
    "d9fc43ee-f79a-4291-8fb6-1a3029c2e7b7": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Jesús Alberto Rodríguez Veloz."),
    "dc21f784-1333-4793-b037-b8feabb8a5ac": ("Eventos de comunicación", "Constancia de participación en Congreso FECA 2022. Presentación/ponencia en congreso de la facultad."),
    "dc758fc6-c240-41d3-9b09-1c981275dd3f": ("Coordinaciones", "Constancia de participación en Reunión del Claustro Académico. Actividad de gestión institucional."),
    "de7f0d04-af41-45d1-9ee7-8060651ff3a0": ("Evaluaciones de programas y proyectos", "Constancia de construcción y mejora de Carpetas PNPC DGO. Trabajo de acreditación del posgrado ante CONAHCYT."),
    "e34ca77d-fad9-41db-9cd4-9373cb6c50cc": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Genaro."),
    "e9907d88-0030-4879-91e8-5b69a71a2eae": ("Trabajos de titulación", "Constancia como secretario en el examen de Jesús Cuevas. Participación en jurado de titulación."),
    "f44e4cfc-62df-4031-8ece-f035b47b4e6f": ("Evaluaciones de programas y proyectos", "Constancia de participación en Comisión Dictaminadora ESDEPED (Estímulos al Desempeño del Personal Docente)."),
    "f7bded43-36af-41f9-bb11-76bcc63876a4": ("Coordinaciones", "Constancia de participación en actividades DGO 2022-B. Actividad de gestión institucional."),
    "f9293134-1f9b-49c0-90ee-960d672da019": ("Trabajos de titulación", "Constancia de asesoría de tesis de Héctor Mauricio Cazares Martínez."),
    "fc1dfcaa-653c-4581-9a7e-54bebf6e2d84": ("Trabajos de titulación", "Constancia como evaluador de la tesis de Alejandro Morales."),
}


def run():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Notion Classifier — Constancias DB                 ║")
    print(f"║  {'DRY RUN — pasa --live para aplicar':52s}║" if DRY_RUN else
          f"║  {'LIVE MODE — ESCRIBIENDO EN NOTION':52s}║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # ── Paso 1: agregar propiedad Notas Rizoma ────────────────────────────────
    print("  Paso 1: Verificando propiedad 'Notas Rizoma'...")
    add_notas_property()
    print()

    # ── Paso 2: actualizar items ──────────────────────────────────────────────
    items = list(MAPPING.items())
    if LIMIT:
        items = items[:LIMIT]
        print(f"  --limit {LIMIT}: procesando {len(items)} items\n")
    else:
        print(f"  Paso 2: Actualizando {len(items)} items...\n")

    # Resumen de clasificaciones
    from collections import Counter
    counts = Counter(sec for _, (sec, _) in MAPPING.items())
    for sec, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {n:3d}  {sec}")
    print()

    if DRY_RUN:
        print("  [DRY RUN] No se realizarán cambios. Pasa --live para actualizar.\n")
        print(f"  Total a actualizar: {len(MAPPING)} items")
        return

    success = failed = 0
    for page_id, (section, note) in items:
        status, resp = update_page(page_id, section, note)
        if status in (200, 201):
            success += 1
            print(f"  ✓ {page_id[:8]}...  →  {section}")
        else:
            failed += 1
            print(f"  ✗ {page_id[:8]}...  FALLÓ HTTP {status}: {str(resp)[:80]}")
        time.sleep(0.5)    # ~2 req/s — conservative to avoid Notion rate limits

    print()
    print("  ══════════════════════════════════════════════════════")
    print(f"  ✓ Actualizados : {success}")
    print(f"  ✗ Fallidos     : {failed}")
    print()


if __name__ == "__main__":
    run()
