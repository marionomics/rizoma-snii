# Requirements — Info needed from Mario

This file tracks what I need you to look up or confirm so the scripts can work correctly.
Fill in each item and tell me when done — I'll update the scripts accordingly.

---

## DONE: Target section URLs

The script needs the exact browser URLs for the 3 sections we want to map.

**How to get them:**
1. Open rizoma.conahcyt.mx in your browser and log in
2. Click **"Trayectoria profesional"** in the top nav to expand it
3. For each of the 3 subsections below, click it and copy the full URL from the address bar

| Section | URL (paste here) |
|---------|-----------------|
| Producción científica | ??? |
| Fortalecimiento y consolidación de la comunidad | ??? |
| Acceso universal al conocimiento | ??? |

Ok, for this I think you still don't fully appreciate just how many fields there are now.

I will write to you only the urls:

https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/articulos
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/libros
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/capitulos
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/reportes
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/informes
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/dossier-o-numero-tematico
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/antologias
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/traducciones
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/prologos-estudios-introductorios
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/curadurias
https://rizoma.conahcyt.mx/trayectoria-profesional/produccion/cientifica-humanistica/base-datos-primarios
https://rizoma.conahcyt.mx/aportaciones/desarrollos-tecnologicos-innovaciones
https://rizoma.conahcyt.mx/aportaciones/propiedades-intelectuales
https://rizoma.conahcyt.mx/aportaciones/transferencias-tecnologicas
https://rizoma.conahcyt.mx/aportaciones/informes-tecnicos
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/cursos-impartidos
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/diplomados-impartidos
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/capacitaciones
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/talleres
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/seminarios
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/docencia/tutorias
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/trabajos-titulacion
https://rizoma.conahcyt.mx/aportaciones/proyectos-investigacion
https://rizoma.conahcyt.mx/aportaciones/planes-estudio
https://rizoma.conahcyt.mx/aportaciones/colaboraciones-interinstitucionales
https://rizoma.conahcyt.mx/aportaciones/coordinaciones
https://rizoma.conahcyt.mx/aportaciones/jurados
https://rizoma.conahcyt.mx/aportaciones/evaluaciones-programas-proyectos
https://rizoma.conahcyt.mx/aportaciones/dictaminaciones-publicaciones
https://rizoma.conahcyt.mx/aportaciones/dictaminaciones-especializadas
https://rizoma.conahcyt.mx/trayectoria-profesional/estancias-investigacion
https://rizoma.conahcyt.mx/trayectoria-profesional/formacion-comunidad/editorial
https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/medios-escritos
https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/audiovisuales-radiofonicos-digitales
https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/museografia-espacios-educacion-no-formal
https://rizoma.conahcyt.mx/trayectoria-profesional/acceso-universal-conocimiento/enlace/eventos-comunicacion


> Note: Each of these might expand into further sub-sections. If so, also list the sub-URLs.

---

## PENDING: Login popup description

There is an initial popup after login that you currently dismiss manually.

**What I need:**
- What does the popup say? (title/heading text)
- Is there a button to close it? What does the button say? (e.g. "Aceptar", "Cerrar", "×")
- Does it appear every time or only once?

| Question | Answer |
|----------|--------|
| Popup title/heading | ??? |
| Close button text | ??? |
| Appears every login? | ??? |

---

## PENDING: Trayectoria profesional — submenu structure

When you expand "Trayectoria profesional" in the nav, what items appear in the dropdown?
List all of them exactly as they appear.

```
Trayectoria profesional
  ├── ???
  ├── ???
  └── ...
```

---

## DONE (no action needed)

- Auth flow: OAuth2/Keycloak confirmed working
- Base API: `/services/msperfil/api/`
- Session save/restore: working
