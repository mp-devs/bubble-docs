#!/usr/bin/env python3
"""
Gerador de Documentação Bubble
===============================
Lê um arquivo .bubble (export do Bubble) e gera um portal HTML
de documentação auto-contido (offline, um único arquivo).

Uso:
    python3 generate_docs.py <arquivo.bubble> [saida.html]

Exemplo:
    python3 generate_docs.py aprimoreagro.bubble docs.html
"""

import json
import sys
import re
import html
from datetime import datetime
from pathlib import Path


def normalize_type(type_str):
    """Converte 'custom.fazenda' em {kind, name, is_list}."""
    if not type_str:
        return {"kind": "unknown", "name": "", "is_list": False}
    is_list = type_str.startswith("list.")
    t = type_str[5:] if is_list else type_str
    if t.startswith("custom."):
        return {"kind": "data_type", "name": t[7:], "is_list": is_list}
    if t.startswith("option."):
        return {"kind": "option_set", "name": t[7:], "is_list": is_list}
    return {"kind": "primitive", "name": t, "is_list": is_list}


def extract_data_types(raw):
    """Extrai todos os Data Types ativos com seus campos."""
    result = []
    for type_id, t in raw.get("user_types", {}).items():
        if not isinstance(t, dict):
            continue
        if t.get("deleted"):
            continue
        display = t.get("display") or type_id
        fields = []
        for field_id, f in (t.get("fields") or {}).items():
            if not isinstance(f, dict):
                continue
            if f.get("deleted"):
                continue
            type_info = normalize_type(f.get("value", ""))
            fields.append({
                "id": field_id,
                "display": f.get("display", field_id),
                "raw_type": f.get("value", ""),
                "type_info": type_info,
            })
        # Ordenar campos alfabeticamente
        fields.sort(key=lambda x: x["display"].lower())
        result.append({
            "id": type_id,
            "display": display,
            "fields": fields,
            "field_count": len(fields),
        })
    result.sort(key=lambda x: x["display"].lower())
    return result


def extract_option_sets(raw):
    """Extrai option sets (enums) com seus valores."""
    result = []
    for os_id, os in raw.get("option_sets", {}).items():
        if not isinstance(os, dict):
            continue
        if os.get("deleted"):
            continue
        values = []
        for v_id, v in (os.get("values") or {}).items():
            if not isinstance(v, dict):
                continue
            if v.get("deleted"):
                continue
            values.append({
                "id": v_id,
                "display": v.get("display", v_id),
                "sort": v.get("sort_factor", 0),
            })
        values.sort(key=lambda x: (x["sort"], x["display"]))
        result.append({
            "id": os_id,
            "display": os.get("display", os_id),
            "values": values,
            "value_count": len(values),
        })
    result.sort(key=lambda x: x["display"].lower())
    return result


def extract_api_events(raw):
    """Extrai API Workflows (expostos e internos)."""
    exposed = []
    internal = []
    for ev_id, ev in raw.get("api", {}).items():
        if not isinstance(ev, dict):
            continue
        if ev.get("type") != "APIEvent":
            continue
        props = ev.get("properties", {}) or {}
        name = props.get("name") or props.get("wf_name") or ev_id
        wf_name = props.get("wf_name", "")
        is_exposed = bool(props.get("expose"))
        params = []
        for _, p in (props.get("parameters") or {}).items():
            if not isinstance(p, dict):
                continue
            type_info = normalize_type(p.get("value", ""))
            params.append({
                "key": p.get("key", ""),
                "raw_type": p.get("value", ""),
                "type_info": type_info,
                "optional": bool(p.get("optional") if isinstance(p.get("optional"), bool) else False),
                "in_url": bool(p.get("in_url") if isinstance(p.get("in_url"), bool) else False),
                "is_list": bool(p.get("is_list") if isinstance(p.get("is_list"), bool) else False),
            })
        event = {
            "id": ev_id,
            "name": name,
            "wf_name": wf_name,
            "exposed": is_exposed,
            "params": params,
            "param_count": len(params),
            "action_count": len(ev.get("actions", {}) or {}),
        }
        if is_exposed:
            exposed.append(event)
        else:
            internal.append(event)
    exposed.sort(key=lambda x: x["name"].lower())
    internal.sort(key=lambda x: x["name"].lower())
    return exposed, internal


def extract_pages(raw):
    """Extrai páginas do app."""
    result = []
    for page_id, p in raw.get("pages", {}).items():
        if not isinstance(p, dict):
            continue
        if p.get("deleted"):
            continue
        props = p.get("properties", {}) or {}
        name = props.get("page_name") or p.get("name") or page_id
        result.append({
            "id": page_id,
            "name": name,
            "element_count": len(p.get("elements", {}) or {}),
        })
    result.sort(key=lambda x: x["name"].lower())
    return result


def build_relationships(data_types):
    """Constrói mapa de relações entre data types (FK)."""
    rels = {}  # type_name -> list of {field, target_type, is_list}
    type_names = {t["display"].lower() for t in data_types}
    for t in data_types:
        tname = t["display"]
        rels[tname] = []
        for f in t["fields"]:
            ti = f["type_info"]
            if ti["kind"] == "data_type":
                rels[tname].append({
                    "field": f["display"],
                    "target": ti["name"],
                    "is_list": ti["is_list"],
                })
    return rels


def generate_html(data_types, option_sets, exposed, internal, pages, rels, app_info):
    """Gera o portal HTML único auto-contido."""
    payload = {
        "app_info": app_info,
        "data_types": data_types,
        "option_sets": option_sets,
        "exposed_endpoints": exposed,
        "internal_workflows": internal,
        "pages": pages,
        "relationships": rels,
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    # Escapar para embed seguro em <script>
    data_json_safe = data_json.replace("</", "<\\/")

    return HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json_safe).replace(
        "__APP_NAME__", html.escape(app_info.get("name", "App Bubble"))
    ).replace("__GEN_DATE__", html.escape(app_info.get("generated_at", "")))


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Documentação — __APP_NAME__</title>
<style>
  :root {
    --bg: #fafaf7;
    --surface: #ffffff;
    --surface-2: #f1efe8;
    --border: rgba(0,0,0,0.08);
    --border-strong: rgba(0,0,0,0.15);
    --text: #1a1a1a;
    --text-2: #5f5e5a;
    --text-3: #888780;
    --accent: #185FA5;
    --accent-bg: #E6F1FB;
    --success: #3B6D11;
    --success-bg: #EAF3DE;
    --warning: #854F0B;
    --warning-bg: #FAEEDA;
    --danger: #A32D2D;
    --danger-bg: #FCEBEB;
    --purple: #534AB7;
    --purple-bg: #EEEDFE;
    --teal: #0F6E56;
    --teal-bg: #E1F5EE;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a1a;
      --surface: #252523;
      --surface-2: #2c2c2a;
      --border: rgba(255,255,255,0.08);
      --border-strong: rgba(255,255,255,0.15);
      --text: #f1efe8;
      --text-2: #b4b2a9;
      --text-3: #888780;
      --accent: #85B7EB;
      --accent-bg: #0C447C;
      --success: #C0DD97;
      --success-bg: #27500A;
      --warning: #FAC775;
      --warning-bg: #633806;
      --danger: #F09595;
      --danger-bg: #791F1F;
      --purple: #AFA9EC;
      --purple-bg: #3C3489;
      --teal: #5DCAA5;
      --teal-bg: #085041;
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 15px;
    line-height: 1.6;
    color: var(--text);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
  }
  .app { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
  .sidebar {
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 20px 0;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
  }
  .sidebar-header {
    padding: 0 20px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .sidebar-header h1 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .sidebar-header p { font-size: 12px; color: var(--text-3); }
  .search-box {
    width: calc(100% - 24px);
    margin: 0 12px 16px;
    padding: 8px 12px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    font-family: inherit;
  }
  .search-box:focus {
    outline: none;
    border-color: var(--accent);
  }
  .nav-section { margin-bottom: 20px; }
  .nav-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-3);
    padding: 8px 20px 4px;
  }
  .nav-item {
    display: flex;
    justify-content: space-between;
    padding: 5px 20px;
    font-size: 13px;
    color: var(--text-2);
    cursor: pointer;
    text-decoration: none;
    border-left: 2px solid transparent;
  }
  .nav-item:hover { background: var(--surface-2); color: var(--text); }
  .nav-item.active {
    background: var(--accent-bg);
    color: var(--accent);
    border-left-color: var(--accent);
  }
  .nav-count {
    font-size: 11px;
    color: var(--text-3);
    background: var(--surface-2);
    padding: 1px 6px;
    border-radius: 10px;
  }
  .main {
    padding: 40px 48px;
    max-width: 1100px;
    overflow-x: hidden;
  }
  .page-header {
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .page-header h2 {
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .page-header p { color: var(--text-2); font-size: 14px; }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin-bottom: 32px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }
  .stat-value {
    font-size: 28px;
    font-weight: 600;
    color: var(--text);
  }
  .stat-label { font-size: 12px; color: var(--text-3); margin-top: 4px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .card-title {
    font-size: 17px;
    font-weight: 600;
  }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
  }
  .badge-accent { background: var(--accent-bg); color: var(--accent); }
  .badge-success { background: var(--success-bg); color: var(--success); }
  .badge-warning { background: var(--warning-bg); color: var(--warning); }
  .badge-danger { background: var(--danger-bg); color: var(--danger); }
  .badge-purple { background: var(--purple-bg); color: var(--purple); }
  .badge-teal { background: var(--teal-bg); color: var(--teal); }
  .badge-gray { background: var(--surface-2); color: var(--text-2); }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th {
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-weight: 500;
    color: var(--text-2);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--surface-2); }
  .type-link {
    color: var(--accent);
    text-decoration: none;
    cursor: pointer;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px;
  }
  .type-link:hover { text-decoration: underline; }
  .type-mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px;
    color: var(--text-2);
  }
  .hidden { display: none !important; }
  .results-count {
    font-size: 13px;
    color: var(--text-3);
    margin-bottom: 20px;
  }
  .detail-section { margin-top: 20px; }
  .detail-section h3 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 10px;
    color: var(--text-2);
  }
  .endpoint-url {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px;
    margin: 12px 0;
    word-break: break-all;
  }
  .endpoint-method {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    background: var(--success-bg);
    color: var(--success);
    margin-right: 8px;
  }
  .relation-list {
    list-style: none;
    padding: 0;
  }
  .relation-list li {
    padding: 6px 0;
    font-size: 13px;
    color: var(--text-2);
  }
  .empty-state {
    padding: 60px 20px;
    text-align: center;
    color: var(--text-3);
  }
  @media (max-width: 768px) {
    .app { grid-template-columns: 1fr; }
    .sidebar { position: static; height: auto; max-height: 400px; }
    .main { padding: 24px 20px; }
  }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>__APP_NAME__</h1>
      <p>Gerado em __GEN_DATE__</p>
    </div>
    <input type="search" class="search-box" id="search" placeholder="Buscar..." autocomplete="off">

    <div class="nav-section">
      <div class="nav-title">Visão geral</div>
      <a class="nav-item" data-view="overview"><span>Início</span></a>
    </div>

    <div class="nav-section">
      <div class="nav-title">API Pública</div>
      <a class="nav-item" data-view="exposed"><span>Endpoints expostos</span><span class="nav-count" id="count-exposed">0</span></a>
    </div>

    <div class="nav-section">
      <div class="nav-title">Estrutura</div>
      <a class="nav-item" data-view="data_types"><span>Data Types</span><span class="nav-count" id="count-dt">0</span></a>
      <a class="nav-item" data-view="option_sets"><span>Option Sets</span><span class="nav-count" id="count-os">0</span></a>
      <a class="nav-item" data-view="internal"><span>Workflows internos</span><span class="nav-count" id="count-int">0</span></a>
      <a class="nav-item" data-view="pages"><span>Páginas</span><span class="nav-count" id="count-pg">0</span></a>
    </div>
  </aside>

  <main class="main" id="main"></main>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;
let currentView = 'overview';
let searchQuery = '';

function badge(text, cls) { return `<span class="badge ${cls}">${text}</span>`; }

function typeBadge(ti, rawType) {
  if (ti.kind === 'data_type') {
    const listTag = ti.is_list ? ' (lista)' : '';
    return `<a class="type-link" data-navigate-type="${ti.name}">→ ${escapeHtml(ti.name)}${listTag}</a>`;
  }
  if (ti.kind === 'option_set') {
    const listTag = ti.is_list ? ' (lista)' : '';
    return `<a class="type-link" data-navigate-os="${ti.name}" style="color: var(--purple);">◇ ${escapeHtml(ti.name)}${listTag}</a>`;
  }
  return `<span class="type-mono">${escapeHtml(rawType || ti.name)}</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function matchesSearch(text, q) {
  if (!q) return true;
  return text.toLowerCase().includes(q.toLowerCase());
}

function renderOverview() {
  const dt = DATA.data_types.length;
  const os = DATA.option_sets.length;
  const ex = DATA.exposed_endpoints.length;
  const iw = DATA.internal_workflows.length;
  const pg = DATA.pages.length;
  const totalFields = DATA.data_types.reduce((s, t) => s + t.field_count, 0);

  return `
    <div class="page-header">
      <h2>Documentação do sistema</h2>
      <p>Gerada automaticamente a partir do export do Bubble em ${escapeHtml(DATA.app_info.generated_at)}</p>
    </div>

    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value">${dt}</div><div class="stat-label">Data Types</div></div>
      <div class="stat-card"><div class="stat-value">${totalFields}</div><div class="stat-label">Campos totais</div></div>
      <div class="stat-card"><div class="stat-value">${ex}</div><div class="stat-label">Endpoints públicos</div></div>
      <div class="stat-card"><div class="stat-value">${iw}</div><div class="stat-label">Workflows internos</div></div>
      <div class="stat-card"><div class="stat-value">${os}</div><div class="stat-label">Option Sets</div></div>
      <div class="stat-card"><div class="stat-value">${pg}</div><div class="stat-label">Páginas</div></div>
    </div>

    <div class="card">
      <div class="card-title" style="margin-bottom: 8px;">Sobre esta documentação</div>
      <p style="color: var(--text-2); font-size: 14px;">
        Esta documentação é gerada automaticamente a partir do export <code class="type-mono">.bubble</code> do seu aplicativo. 
        Ela contém a estrutura completa de dados, endpoints de API, workflows e páginas.
      </p>
      <div class="detail-section">
        <h3>Como atualizar</h3>
        <p style="color: var(--text-2); font-size: 14px;">
          1. Exporte seu app novamente em <strong>Settings → General → Export application</strong><br>
          2. Rode o gerador: <code class="type-mono">python3 generate_docs.py novo_export.bubble</code><br>
          3. Hospede o novo HTML onde quiser (GitHub Pages, Vercel, Netlify, S3).
        </p>
      </div>
    </div>

    <div class="card">
      <div class="card-title" style="margin-bottom: 12px;">Data Types com mais campos</div>
      <table>
        <thead><tr><th>Tipo</th><th style="text-align:right">Campos</th></tr></thead>
        <tbody>
          ${[...DATA.data_types].sort((a,b)=>b.field_count-a.field_count).slice(0,10).map(t =>
            `<tr><td><a class="type-link" data-navigate-type="${t.display}">${escapeHtml(t.display)}</a></td><td style="text-align:right">${t.field_count}</td></tr>`
          ).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderDataTypesList() {
  const filtered = DATA.data_types.filter(t => matchesSearch(t.display, searchQuery));
  return `
    <div class="page-header">
      <h2>Data Types</h2>
      <p>Estruturas de dados (tabelas) do sistema</p>
    </div>
    <div class="results-count">${filtered.length} de ${DATA.data_types.length} tipos</div>
    ${filtered.map(t => {
      const rels = DATA.relationships[t.display] || [];
      return `
        <div class="card">
          <div class="card-header">
            <div class="card-title">${escapeHtml(t.display)}</div>
            <div>
              ${badge(`${t.field_count} campos`, 'badge-gray')}
              ${rels.length ? badge(`${rels.length} relações`, 'badge-accent') : ''}
            </div>
          </div>
          ${t.fields.length ? `
            <table>
              <thead><tr><th style="width:40%">Campo</th><th>Tipo</th></tr></thead>
              <tbody>
                ${t.fields.map(f => `
                  <tr>
                    <td><strong>${escapeHtml(f.display)}</strong></td>
                    <td>${typeBadge(f.type_info, f.raw_type)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : '<p style="color: var(--text-3); font-size: 13px;">Sem campos definidos.</p>'}
        </div>
      `;
    }).join('')}
    ${filtered.length === 0 ? '<div class="empty-state">Nenhum resultado.</div>' : ''}
  `;
}

function renderOptionSets() {
  const filtered = DATA.option_sets.filter(o => matchesSearch(o.display, searchQuery));
  return `
    <div class="page-header">
      <h2>Option Sets</h2>
      <p>Listas de valores pré-definidos (enums)</p>
    </div>
    <div class="results-count">${filtered.length} de ${DATA.option_sets.length} option sets</div>
    ${filtered.map(o => `
      <div class="card">
        <div class="card-header">
          <div class="card-title">${escapeHtml(o.display)}</div>
          ${badge(`${o.value_count} opções`, 'badge-purple')}
        </div>
        ${o.values.length ? `
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            ${o.values.map(v => `<span class="badge badge-gray">${escapeHtml(v.display)}</span>`).join('')}
          </div>
        ` : '<p style="color: var(--text-3); font-size: 13px;">Sem valores.</p>'}
      </div>
    `).join('')}
    ${filtered.length === 0 ? '<div class="empty-state">Nenhum resultado.</div>' : ''}
  `;
}

function renderEndpoints(events, title, subtitle) {
  const filtered = events.filter(e => matchesSearch(e.name + ' ' + e.wf_name, searchQuery));
  return `
    <div class="page-header">
      <h2>${title}</h2>
      <p>${subtitle}</p>
    </div>
    <div class="results-count">${filtered.length} de ${events.length} workflows</div>
    ${filtered.map(e => `
      <div class="card">
        <div class="card-header">
          <div class="card-title">${escapeHtml(e.name)}</div>
          ${e.exposed ? badge('Público', 'badge-success') : badge('Interno', 'badge-gray')}
        </div>
        ${e.wf_name ? `
          <div class="endpoint-url">
            ${e.exposed ? '<span class="endpoint-method">POST</span>' : ''}
            /api/1.1/wf/${escapeHtml(e.wf_name)}
          </div>
        ` : ''}
        ${e.params.length ? `
          <div class="detail-section">
            <h3>Parâmetros (${e.params.length})</h3>
            <table>
              <thead><tr><th>Nome</th><th>Tipo</th><th>Opcional</th></tr></thead>
              <tbody>
                ${e.params.map(p => `
                  <tr>
                    <td><strong>${escapeHtml(p.key)}</strong></td>
                    <td>${typeBadge(p.type_info, p.raw_type)}</td>
                    <td>${p.optional ? badge('Sim', 'badge-warning') : badge('Não', 'badge-gray')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : '<p style="color: var(--text-3); font-size: 13px;">Sem parâmetros.</p>'}
        <div class="detail-section">
          <p style="font-size: 12px; color: var(--text-3);">Ações no workflow: ${e.action_count}</p>
        </div>
      </div>
    `).join('')}
    ${filtered.length === 0 ? '<div class="empty-state">Nenhum resultado.</div>' : ''}
  `;
}

function renderPages() {
  const filtered = DATA.pages.filter(p => matchesSearch(p.name, searchQuery));
  return `
    <div class="page-header">
      <h2>Páginas</h2>
      <p>Telas do aplicativo</p>
    </div>
    <div class="results-count">${filtered.length} de ${DATA.pages.length} páginas</div>
    <div class="card">
      <table>
        <thead><tr><th>Página</th><th style="text-align:right">Elementos</th></tr></thead>
        <tbody>
          ${filtered.map(p => `
            <tr>
              <td><strong>${escapeHtml(p.name)}</strong></td>
              <td style="text-align:right">${p.element_count}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    ${filtered.length === 0 ? '<div class="empty-state">Nenhum resultado.</div>' : ''}
  `;
}

function renderTypeDetail(name) {
  const t = DATA.data_types.find(x => x.display === name);
  if (!t) return '<div class="empty-state">Tipo não encontrado.</div>';
  const rels = DATA.relationships[t.display] || [];
  // Achar quem aponta para este tipo
  const incomingRels = [];
  for (const [src, rs] of Object.entries(DATA.relationships)) {
    for (const r of rs) {
      if (r.target === t.display) incomingRels.push({ source: src, ...r });
    }
  }

  return `
    <div class="page-header">
      <p style="font-size: 12px; color: var(--text-3); margin-bottom: 4px;"><a class="type-link" data-view="data_types">← Data Types</a></p>
      <h2>${escapeHtml(t.display)}</h2>
      <p>${t.field_count} campos · ${rels.length} relações de saída · ${incomingRels.length} relações de entrada</p>
    </div>

    <div class="card">
      <div class="card-title" style="margin-bottom: 12px;">Campos</div>
      <table>
        <thead><tr><th style="width:40%">Campo</th><th>Tipo</th></tr></thead>
        <tbody>
          ${t.fields.map(f => `
            <tr>
              <td><strong>${escapeHtml(f.display)}</strong></td>
              <td>${typeBadge(f.type_info, f.raw_type)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>

    ${incomingRels.length ? `
      <div class="card">
        <div class="card-title" style="margin-bottom: 12px;">Referenciado por</div>
        <ul class="relation-list">
          ${incomingRels.map(r => `
            <li><a class="type-link" data-navigate-type="${escapeHtml(r.source)}">${escapeHtml(r.source)}</a> → campo <strong>${escapeHtml(r.field)}</strong>${r.is_list ? ' (lista)' : ''}</li>
          `).join('')}
        </ul>
      </div>
    ` : ''}
  `;
}

function renderOptionSetDetail(name) {
  const o = DATA.option_sets.find(x => x.display === name || x.id === name);
  if (!o) return '<div class="empty-state">Option set não encontrado.</div>';
  return `
    <div class="page-header">
      <p style="font-size: 12px; color: var(--text-3); margin-bottom: 4px;"><a class="type-link" data-view="option_sets">← Option Sets</a></p>
      <h2>${escapeHtml(o.display)}</h2>
      <p>${o.value_count} valores</p>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>Valor</th></tr></thead>
        <tbody>
          ${o.values.map(v => `<tr><td><strong>${escapeHtml(v.display)}</strong></td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function render() {
  const main = document.getElementById('main');
  let html = '';
  if (currentView === 'overview') html = renderOverview();
  else if (currentView === 'data_types') html = renderDataTypesList();
  else if (currentView === 'option_sets') html = renderOptionSets();
  else if (currentView === 'exposed') html = renderEndpoints(DATA.exposed_endpoints, 'Endpoints públicos', 'Workflows expostos como API pública');
  else if (currentView === 'internal') html = renderEndpoints(DATA.internal_workflows, 'Workflows internos', 'Workflows de backend não expostos');
  else if (currentView === 'pages') html = renderPages();
  else if (currentView.startsWith('type:')) html = renderTypeDetail(currentView.slice(5));
  else if (currentView.startsWith('os:')) html = renderOptionSetDetail(currentView.slice(3));
  main.innerHTML = html;
  window.scrollTo(0, 0);

  // Update active nav
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === currentView);
  });
}

function setView(v) {
  currentView = v;
  searchQuery = '';
  document.getElementById('search').value = '';
  render();
}

// Event delegation
document.addEventListener('click', e => {
  const navEl = e.target.closest('[data-view]');
  if (navEl) {
    e.preventDefault();
    setView(navEl.dataset.view);
    return;
  }
  const typeEl = e.target.closest('[data-navigate-type]');
  if (typeEl) {
    e.preventDefault();
    currentView = 'type:' + typeEl.dataset.navigateType;
    render();
    return;
  }
  const osEl = e.target.closest('[data-navigate-os]');
  if (osEl) {
    e.preventDefault();
    currentView = 'os:' + osEl.dataset.navigateOs;
    render();
    return;
  }
});

document.getElementById('search').addEventListener('input', e => {
  searchQuery = e.target.value;
  render();
});

// Contagens iniciais
document.getElementById('count-dt').textContent = DATA.data_types.length;
document.getElementById('count-os').textContent = DATA.option_sets.length;
document.getElementById('count-exposed').textContent = DATA.exposed_endpoints.length;
document.getElementById('count-int').textContent = DATA.internal_workflows.length;
document.getElementById('count-pg').textContent = DATA.pages.length;

render();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("docs.html")

    if not input_path.exists():
        print(f"Erro: arquivo '{input_path}' não encontrado.")
        sys.exit(1)

    print(f"📖 Lendo {input_path.name}...")
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print("🔎 Extraindo data types...")
    data_types = extract_data_types(raw)

    print("🔎 Extraindo option sets...")
    option_sets = extract_option_sets(raw)

    print("🔎 Extraindo API workflows...")
    exposed, internal = extract_api_events(raw)

    print("🔎 Extraindo páginas...")
    pages = extract_pages(raw)

    print("🔗 Mapeando relações...")
    rels = build_relationships(data_types)

    app_info = {
        "name": input_path.stem,
        "version": raw.get("app_version", ""),
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    print("🎨 Gerando HTML...")
    html_out = generate_html(data_types, option_sets, exposed, internal, pages, rels, app_info)

    output_path.write_text(html_out, encoding="utf-8")

    print()
    print(f"✅ Documentação gerada: {output_path}")
    print(f"   📊 {len(data_types)} Data Types ({sum(t['field_count'] for t in data_types)} campos)")
    print(f"   🌐 {len(exposed)} endpoints públicos, {len(internal)} workflows internos")
    print(f"   🏷  {len(option_sets)} option sets")
    print(f"   📄 {len(pages)} páginas")
    print(f"   📦 Tamanho: {output_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
