#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_bci.py  —  Generador de la web app "BCI Jobs"
====================================================
Baja las ofertas del portal trabajaenbci.cl (endpoint Elasticsearch),
filtra por tu perfil de palabras clave y genera un index.html tipo PWA,
igualito a tu Entel Jobs.

POR QUE SE CORRE DEL LADO SERVIDOR (y no en el navegador)
---------------------------------------------------------
El endpoint de Bci responde con:
    Access-Control-Allow-Origin: https://trabajaenbci.cl
o sea, SOLO acepta llamadas desde su propio dominio. Un navegador en
github.io NO puede bajar los datos directo (lo bloquea CORS). Por eso este
script corre en Python (donde CORS no aplica) — localmente o dentro de
GitHub Actions — y publica el HTML ya armado en GitHub Pages.

Requisitos:  pip install requests
Uso local:   python radar_bci.py           (baja datos y abre el HTML)
Uso CI:      python radar_bci.py --ci       (no abre navegador)
"""

import os
import re
import sys
import json
import html
import urllib.parse
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("Falta 'requests'.  Instala con:  pip install requests")

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
BASE = "https://trabajaenbci.cl"
API = f"{BASE}/api/v3/bci_portals/_search"
QUERY = {"query": {"match_all": {}}, "size": 100}   # trae todas (hay ~36)
UA = "Mozilla/5.0 (radar_bci)"

# Tu perfil de palabras clave (el mismo del radar Entel).
KEYWORDS = [
    "voz", "voip", "sip", "carrier", "wholesale", "noc", "redes", "network",
    "telecom", "infraestructura", "implementacion", "implementación", "core",
    "ops", "pbx", "trunk", "interconexion", "interconexión", "numeracion",
    "numeración", "ingenieria", "ingeniería", "sistemas", "routing", "fibra",
    "soporte tecnico", "soporte técnico",
]
AREAS = [
    "Carrier wholesale", "VoIP / SIP", "NOC", "Redes / Network",
    "Implementación", "Infraestructura TI", "Core voz", "Ops fijo / móvil",
]

CACHE_FILE = "bci_offers_cache.json"
OUTPUT_HTML = "index.html"

# ----------------------------------------------------------------------
# DESCARGA
# ----------------------------------------------------------------------
def fetch_offers():
    """Devuelve (ofertas, fuente). Cae a caché si no hay red."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
    try:
        # 1) primer GET: obtiene cookies (incl. XSRF-TOKEN) por si el POST lo pide
        s.get(f"{BASE}/oportunidades-laborales", timeout=25)
        xsrf = s.cookies.get("XSRF-TOKEN", "")
        headers = {
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/oportunidades-laborales",
        }
        if xsrf:
            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(xsrf)
        # 2) POST al endpoint Elasticsearch
        r = s.post(API, json=QUERY, headers=headers, timeout=25)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        offers = [h["_source"] for h in hits if isinstance(h, dict) and "_source" in h]
        if offers:
            _save_cache(offers)
            return offers, API
    except Exception as e:
        print(f"[aviso] fallo la descarga en vivo: {e}")
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f), "caché offline"
    return [], None


def _save_cache(offers):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(offers, f, ensure_ascii=False)
    except Exception:
        pass


# ----------------------------------------------------------------------
# NORMALIZACION
# ----------------------------------------------------------------------
def _strip_html(t):
    return re.sub(r"<[^>]+>", " ", t or "")


def _days_ago(value):
    if not value:
        return None
    s = str(value).strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return max((datetime.now() - datetime.strptime(s, f)).days, 0)
        except ValueError:
            pass
    clean = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", s)
    for f in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return max((datetime.now() - datetime.strptime(clean, f)).days, 0)
        except ValueError:
            pass
    return None


def normalize(o):
    commune = (o.get("commune_name") or "").strip()
    region = (o.get("region_name") or "").strip()
    oid = o.get("id")
    pub = o.get("published_at_date_text") or o.get("created_at")
    blob = " ".join(_strip_html(str(o.get(k, ""))) for k in (
        "title", "description", "long_description", "excluding_requirements",
        "desirable_knowledge", "bci_department_title"))
    url = o.get("public_url") or (f"/offers/{oid}" if oid else "")
    return {
        "title": (o.get("title") or "(sin título)").strip(),
        "commune": commune,
        "region": region,
        "url": BASE + url if url.startswith("/") else (url or BASE),
        "days": _days_ago(pub),
        "remote_text": (o.get("archetype_text") or "").strip(),
        "remote_days": o.get("remote_days") or 0,
        "dept": (o.get("bci_department_title") or "").strip(),
        "text": blob.lower(),
    }


def matches_profile(o):
    return any(kw in o["text"] for kw in KEYWORDS)


# ----------------------------------------------------------------------
# HTML  (mismo layout que tu Entel Jobs, + PWA)
# ----------------------------------------------------------------------
def _card(o):
    days = o["days"]
    chips = []
    if o["commune"]:
        chips.append(f'<span class="chip">📍 {html.escape(o["commune"])}</span>')
    if days is not None:
        chips.append(f'<span class="chip">{days} día{"s" if days != 1 else ""}</span>')
    if days is not None and days <= 7:
        chips.append('<span class="chip hot">🔥 Reciente</span>')
    if o["remote_days"] and o["remote_days"] > 0:
        chips.append(f'<span class="chip rem">🏠 {o["remote_days"]} días remotos</span>')
    dept = f'<div class="dept">{html.escape(o["dept"])}</div>' if o["dept"] else ""
    return f"""
      <div class="job">
        <h3>{html.escape(o['title'])}</h3>{dept}
        <div class="meta">{''.join(chips)}</div>
        <a class="link" href="{html.escape(o['url'])}" target="_blank" rel="noopener">Ver oferta ↗</a>
      </div>"""


def build_html(offers, source):
    norm = [normalize(o) for o in offers]
    matched = [o for o in norm if matches_profile(o)]
    recent = [o for o in norm if o["days"] is not None and o["days"] <= 7]
    stamp = datetime.now().strftime("%d-%m-%Y, %I:%M %p").lower()
    para_ti = "".join(_card(o) for o in matched) or '<p class="empty">Sin coincidencias con tu perfil ahora.</p>'
    todas = "".join(_card(o) for o in norm) or '<p class="empty">No se cargaron ofertas.</p>'
    kw_chips = "".join(f'<span class="kw">{html.escape(k)}</span>' for k in dict.fromkeys(KEYWORDS))
    area_chips = "".join(f'<span class="kw">{html.escape(a)}</span>' for a in AREAS)
    src = "sitio oficial trabajaenbci.cl" if source and source.startswith("http") else html.escape(source or "sin fuente")

    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a2c6b">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-192.png">
<title>BCI Jobs</title>
<style>
  :root {{ --navy:#0a2c6b; --navy2:#0033a0; --amber:#c25e00; --amberbg:#fdecd8;
          --green:#0a7d3c; --greenbg:#e4f4ea; --ink:#1a2233; --muted:#6b7684;
          --line:#e5e8ef; --bg:#f6f8fb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--ink); }}
  .wrap {{ max-width:560px; margin:0 auto; }}
  header {{ background:#fff; padding:20px 20px 0; display:flex; justify-content:space-between; align-items:flex-start; }}
  header h1 {{ margin:0; color:var(--navy); font-size:29px; font-weight:800; }}
  header .sub {{ color:var(--muted); font-size:14px; margin:2px 0 16px; }}
  .refresh {{ background:#eef1fb; color:var(--navy2); border:none; border-radius:22px;
             padding:9px 16px; font-size:15px; font-weight:700; cursor:pointer; white-space:nowrap; }}
  .tabs {{ display:flex; gap:22px; border-bottom:1px solid var(--line); padding:0 20px; background:#fff; position:sticky; top:0; z-index:5; }}
  .tab {{ padding:12px 0 10px; font-size:16px; color:var(--muted); font-weight:600; background:none; border:none; border-bottom:3px solid transparent; cursor:pointer; }}
  .tab.active {{ color:var(--navy); border-color:var(--navy); }}
  .badge {{ background:var(--navy); color:#fff; border-radius:20px; padding:1px 9px; font-size:13px; margin-left:6px; }}
  .panel {{ display:none; padding:16px 16px 48px; }}
  .panel.active {{ display:block; }}
  .install {{ display:none; background:#eef4ff; border:1px solid #d6e2ff; border-radius:12px; padding:12px 14px; margin-bottom:14px; align-items:center; justify-content:space-between; }}
  .install b {{ font-weight:600; }}
  .install button {{ background:var(--navy2); color:#fff; border:none; border-radius:8px; padding:8px 16px; font-weight:700; cursor:pointer; }}
  .status {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:13px 15px; color:var(--muted); font-size:14px; margin-bottom:14px; }}
  .status b {{ color:var(--ink); }}
  .stats {{ display:flex; gap:12px; margin-bottom:14px; }}
  .stat {{ flex:1; background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px; text-align:center; }}
  .stat .n {{ font-size:34px; font-weight:800; color:var(--navy); }}
  .stat .l {{ font-size:13px; color:var(--muted); }}
  .job {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--navy); border-radius:12px; padding:15px; margin-bottom:12px; }}
  .job h3 {{ margin:0 0 4px; font-size:18px; }}
  .dept {{ color:var(--muted); font-size:13px; margin-bottom:9px; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }}
  .chip {{ background:#eef1f6; color:#48505e; border-radius:16px; padding:4px 11px; font-size:13px; }}
  .chip.hot {{ background:var(--amberbg); color:var(--amber); font-weight:600; }}
  .chip.rem {{ background:var(--greenbg); color:var(--green); }}
  .link {{ color:var(--navy2); font-weight:700; text-decoration:none; font-size:15px; }}
  .empty {{ color:var(--muted); text-align:center; padding:30px; }}
  .sec {{ color:var(--muted); font-size:12px; letter-spacing:.06em; font-weight:700; margin:22px 4px 10px; }}
  .kw {{ display:inline-block; border:1px solid var(--line); background:#fff; border-radius:18px; padding:6px 13px; margin:0 6px 8px 0; font-size:14px; }}
  .how {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:15px; font-size:14px; line-height:1.5; color:#333; }}
  .search {{ width:100%; padding:13px 16px; border:1px solid var(--line); border-radius:14px; font-size:16px; margin-bottom:12px; }}
</style></head>
<body><div class="wrap">
  <header>
    <div><h1>BCI Jobs</h1><div class="sub">Seguimiento personalizado · Mario Bustos</div></div>
    <button class="refresh" onclick="location.reload()">🔄 Actualizar</button>
  </header>
  <div class="tabs">
    <button class="tab active" onclick="go(0)">Para ti <span class="badge">{len(matched)}</span></button>
    <button class="tab" onclick="go(1)">Todas <span class="badge">{len(norm)}</span></button>
    <button class="tab" onclick="go(2)">Mi perfil</button>
  </div>

  <div class="panel active">
    <div class="install" id="ins"><span>📲 <b>Agrégala a tu pantalla de inicio</b></span><button id="insBtn">Instalar</button></div>
    <div class="status">● <b>{len(norm)} cargos cargados</b> · {stamp}</div>
    <div class="stats">
      <div class="stat"><div class="n">{len(matched)}</div><div class="l">Calzan con tu perfil</div></div>
      <div class="stat"><div class="n">{len(recent)}</div><div class="l">Publicadas ≤7 días</div></div>
    </div>
    {para_ti}
  </div>

  <div class="panel">
    <input class="search" id="q" placeholder="Buscar cargo o ciudad..." oninput="filtrar()">
    <div id="all">{todas}</div>
  </div>

  <div class="panel">
    <div class="sec">ÚLTIMA ACTUALIZACIÓN</div>
    <div class="status">{stamp} · fuente: {src}</div>
    <div class="sec">PALABRAS CLAVE ACTIVAS</div>
    <div>{kw_chips}</div>
    <div class="sec">ÁREAS OBJETIVO</div>
    <div>{area_chips}</div>
    <div class="sec">CÓMO FUNCIONA</div>
    <div class="how">Un proceso automático consulta el portal oficial de <b>trabajaenbci.cl</b>,
    filtra por tu perfil de palabras clave y publica esta app. Cuando no hay conexión,
    muestra los datos guardados de la última consulta (caché offline).</div>
  </div>
</div>
<script>
  function go(i){{
    document.querySelectorAll('.tab').forEach((t,n)=>t.classList.toggle('active',n===i));
    document.querySelectorAll('.panel').forEach((p,n)=>p.classList.toggle('active',n===i));
    window.scrollTo(0,0);
  }}
  function filtrar(){{
    var q=document.getElementById('q').value.toLowerCase();
    document.querySelectorAll('#all .job').forEach(function(c){{
      c.style.display = c.innerText.toLowerCase().includes(q) ? '' : 'none';
    }});
  }}
  let deferred;
  window.addEventListener('beforeinstallprompt',function(e){{
    e.preventDefault(); deferred=e; document.getElementById('ins').style.display='flex';
  }});
  document.getElementById('insBtn').onclick=function(){{ if(deferred){{deferred.prompt();deferred=null;document.getElementById('ins').style.display='none';}} }};
  if('serviceWorker' in navigator){{ navigator.serviceWorker.register('sw.js').catch(()=>{{}}); }}
</script>
</body></html>"""


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    ci = "--ci" in sys.argv
    offers, source = fetch_offers()
    if not offers:
        print("No se obtuvieron ofertas y no hay caché. Revisa conexión / endpoint.")
        sys.exit(1)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(build_html(offers, source))
    print(f"OK · {len(offers)} ofertas · fuente: {source} · generado {OUTPUT_HTML}")
    if not ci:
        try:
            import webbrowser
            webbrowser.open("file://" + os.path.abspath(OUTPUT_HTML))
        except Exception:
            pass


if __name__ == "__main__":
    main()
