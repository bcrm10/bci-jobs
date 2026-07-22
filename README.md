# BCI Jobs

App de seguimiento personalizado de ofertas en Bci (trabajaenbci.cl), equivalente a Entel Jobs.

## Por qué no es 100% client-side como Entel
El endpoint de Bci (`/api/v3/bci_portals/_search`) responde con
`Access-Control-Allow-Origin: https://trabajaenbci.cl`, o sea solo acepta llamadas
desde su propio dominio. Un navegador en github.io no puede bajar los datos directo (CORS).
Solución: los datos se bajan del lado servidor (Python) dentro de GitHub Actions y se
publica el HTML ya armado en GitHub Pages. Resultado idéntico: PWA instalable, offline, etc.

## Estructura
- `radar_bci.py` — baja las ofertas y genera `index.html`
- `index.html` — la app (se regenera en cada corrida)
- `manifest.webmanifest`, `sw.js`, `icon-192.png`, `icon-512.png` — PWA
- `.github/workflows/update.yml` — automatización (cada 3 h + manual)

## Publicar (una sola vez)
1. Crea el repo `bci-jobs` en github.com/bcrm10 (vacío).
2. Sube todos estos archivos:
   ```
   git init
   git add -A
   git commit -m "BCI Jobs"
   git branch -M main
   git remote add origin https://github.com/bcrm10/bci-jobs.git
   git push -u origin main
   ```
3. En el repo → Settings → Pages → Source: `Deploy from a branch`, branch `main` / `(root)`.
4. Settings → Actions → General → Workflow permissions: `Read and write permissions`.
5. Listo: la app queda en https://bcrm10.github.io/bci-jobs/
   El workflow la refresca cada 3 h; también puedes correrlo a mano en la pestaña Actions.

## Correr local (opcional)
```
pip install requests
python radar_bci.py
```
