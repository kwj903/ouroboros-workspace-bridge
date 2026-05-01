from __future__ import annotations

import html

VALID_SERVER_TABS = {"overview", "services", "processes", "connection", "environment", "tools", "diagnostics"}
SERVER_TAB_LABELS = {
    "overview": "개요",
    "services": "서버",
    "processes": "프로세스",
    "connection": "연결",
    "environment": "환경",
    "tools": "로컬 도구",
    "diagnostics": "진단",
}


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def normalize_server_tab(value: str | None) -> str:
    tab = (value or "overview").strip().lower()
    if tab not in VALID_SERVER_TABS:
        return "overview"
    return tab


def primary_nav_html(active: str) -> str:
    items = (
        ("pending", "/pending", "승인"),
        ("history", "/history", "이력/결과"),
        ("servers", "/servers", "관리"),
    )
    links: list[str] = []
    for key, href, label in items:
        classes = ["nav-link"]
        aria = ""
        if key == active:
            classes.append("is-active")
            aria = ' aria-current="page"'
        links.append(
            f'<a class="{" ".join(classes)}" href="{escape(href)}"{aria}>{escape(label)}</a>'
        )
    return '<nav class="nav">' + "".join(links) + "</nav>"


def management_nav_html(current_tab: str) -> str:
    current_tab = normalize_server_tab(current_tab)
    links: list[str] = []
    for tab in ("overview", "services", "processes", "connection", "environment", "tools", "diagnostics"):
        classes = ["side-link"]
        aria = ""
        if tab == current_tab:
            classes.append("is-active")
            aria = ' aria-current="page"'
        links.append(
            f'<a class="{" ".join(classes)}" href="/servers?tab={escape(tab)}"{aria}>'
            f"{escape(SERVER_TAB_LABELS[tab])}</a>"
        )
    return '<div class="side-nav">' + "".join(links) + "</div>"


def app_shell(
    title: str,
    body: str,
    active_nav: str,
    subtitle: str = "",
    server_tab: str | None = None,
) -> bytes:
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --surface: rgba(127, 127, 127, 0.08);
      --surface-strong: rgba(127, 127, 127, 0.12);
      --border: rgba(127, 127, 127, 0.24);
      --accent: #2563eb;
      --accent-soft: rgba(37, 99, 235, 0.12);
      --success: #15803d;
      --warning: #b45309;
      --danger: #dc2626;
    }}
    *,
    *::before,
    *::after {{
      box-sizing: border-box;
    }}
    html {{
      max-width: 100%;
      overflow-x: hidden;
    }}
    body {{
      margin: 0 auto;
      padding: 0;
      max-width: 100%;
      overflow-x: hidden;
      line-height: 1.6;
      background:
        linear-gradient(180deg, rgba(127, 127, 127, 0.05), transparent 260px);
    }}
    :focus-visible {{
      outline: 3px solid rgba(37, 99, 235, 0.45);
      outline-offset: 3px;
    }}
    .app-shell {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
      max-width: 100vw;
      overflow-x: hidden;
    }}
    .sidebar {{
      border-right: 1px solid var(--border);
      padding: 28px 20px;
      background: rgba(127, 127, 127, 0.05);
    }}
    .brand {{
      display: grid;
      gap: 4px;
      margin-bottom: 24px;
    }}
    .brand-title {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.25;
    }}
    .brand-subtitle {{
      color: inherit;
      opacity: 0.72;
      font-size: 14px;
    }}
    .sidebar-section {{
      display: grid;
      gap: 10px;
      margin-top: 18px;
    }}
    .sidebar-label {{
      color: inherit;
      opacity: 0.62;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .main-content {{
      min-width: 0;
      padding: 32px min(5vw, 56px) 56px;
      overflow-x: hidden;
    }}
    .content-inner {{
      display: grid;
      gap: 22px;
      width: 100%;
      max-width: 1040px;
      min-width: 0;
    }}
    .page-header {{
      display: grid;
      gap: 8px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.35rem);
      line-height: 1.2;
    }}
    h2, h3 {{
      margin-top: 0;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .nav {{
      display: grid;
      gap: 8px;
    }}
    .nav-link {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-weight: 700;
    }}
    .nav-link:hover,
    .nav-link.is-active {{
      text-decoration: none;
    }}
    .nav-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .subnav {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin: 12px 0 18px;
    }}
    .subnav-link {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-size: 14px;
      font-weight: 600;
    }}
    .subnav-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .meta,
    .meta-label {{
      opacity: 0.78;
      font-size: 14px;
    }}
    .card,
    .metric,
    .notice {{
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--surface);
    }}
    .card {{
      padding: 20px;
      margin: 0;
      min-width: 0;
      max-width: 100%;
    }}
    .card.is-failed {{
      border-color: rgba(220, 38, 38, 0.36);
      background: rgba(220, 38, 38, 0.07);
    }}
    .metric {{
      padding: 18px;
    }}
    .metric-link {{
      display: block;
      color: inherit;
    }}
    .metric-link:hover {{
      text-decoration: none;
      border-color: rgba(37, 99, 235, 0.32);
    }}
    .metric-value {{
      font-size: 28px;
      font-weight: 800;
      line-height: 1.1;
      margin: 8px 0 4px;
    }}
    .notice {{
      padding: 16px 18px;
    }}
    .stack {{
      display: grid;
      gap: 16px;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .section-title {{
      display: grid;
      gap: 6px;
      margin-bottom: 4px;
    }}
    .side-nav {{
      display: grid;
      gap: 8px;
    }}
    .side-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-weight: 600;
    }}
    .side-link:hover,
    .side-link.is-active {{
      text-decoration: none;
    }}
    .side-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .kv {{
      display: grid;
      gap: 0;
    }}
    .kv-row {{
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
      padding: 12px 0;
      border-top: 1px solid var(--border);
    }}
    .kv-row:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .kv-label {{
      font-weight: 700;
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .kv-value {{
      min-width: 0;
      display: flex;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 8px;
      overflow-wrap: anywhere;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
    }}
    .data-table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }}
    .data-table th,
    .data-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      opacity: 0.72;
    }}
    .data-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .process-table {{
      min-width: 1280px;
      table-layout: auto;
    }}
    .process-table th:nth-child(1),
    .process-table td:nth-child(1) {{
      width: 88px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(2),
    .process-table td:nth-child(2) {{
      width: 72px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(3),
    .process-table td:nth-child(3),
    .process-table th:nth-child(4),
    .process-table td:nth-child(4),
    .process-table th:nth-child(5),
    .process-table td:nth-child(5) {{
      width: 108px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(6),
    .process-table td:nth-child(6) {{
      min-width: 150px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(7),
    .process-table td:nth-child(7),
    .process-table th:nth-child(8),
    .process-table td:nth-child(8) {{
      min-width: 120px;
    }}
    .process-table td:nth-child(2) code,
    .process-table td:nth-child(6) code {{
      word-break: normal;
      white-space: nowrap;
    }}
    .process-table td:nth-child(7) code,
    .process-table td:nth-child(8) code {{
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .process-table th:nth-child(9),
    .process-table td:nth-child(9) {{
      width: 200px;
      white-space: nowrap;
    }}
    .service-controls {{
      display: inline-flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .service-controls button {{
      padding: 7px 10px;
      font-size: 13px;
    }}
    .mode-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin-top: 14px;
      min-width: 0;
    }}
    .mode-option {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
      min-height: 170px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
    }}
    .mode-option.selected {{
      border-color: rgba(37, 99, 235, 0.55);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }}
    .mode-option.warning {{
      border-color: rgba(220, 38, 38, 0.28);
    }}
    .mode-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 6px;
      font-weight: 800;
    }}
    .banner {{
      border-radius: 14px;
      padding: 12px 14px;
      margin: 0 0 16px;
      border: 1px solid var(--border);
    }}
    .banner.info {{
      background: rgba(37, 99, 235, 0.08);
      border-color: rgba(37, 99, 235, 0.16);
    }}
    .banner.warning {{
      background: rgba(220, 38, 38, 0.08);
      border-color: rgba(220, 38, 38, 0.18);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      max-width: 100%;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 13px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge.ok {{
      color: var(--success);
      background: rgba(21, 128, 61, 0.12);
      border-color: rgba(21, 128, 61, 0.18);
    }}
    .badge.warn {{
      color: var(--warning);
      background: rgba(180, 83, 9, 0.12);
      border-color: rgba(180, 83, 9, 0.2);
    }}
    .badge.danger {{
      color: var(--danger);
      background: rgba(220, 38, 38, 0.12);
      border-color: rgba(220, 38, 38, 0.2);
    }}
    .badge.neutral {{
      background: var(--surface-strong);
      border-color: var(--border);
    }}
    .button-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}
    form.inline {{
      display: inline;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    code {{
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    pre {{
      background: var(--surface-strong);
      border-radius: 12px;
      padding: 14px;
      max-width: 100%;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      overflow-x: auto;
      margin: 0;
    }}
    textarea {{
      display: block;
      width: 100%;
      max-width: 100%;
      min-width: 0;
    }}
    button {{
      font-size: 15px;
      font-weight: 700;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid #888;
      cursor: pointer;
    }}
    .secondary {{
      background: var(--surface-strong);
      color: inherit;
      border-color: var(--border);
    }}
    .approve {{
      background: #16a34a;
      color: white;
      border-color: #16a34a;
    }}
    .reject {{
      background: #dc2626;
      color: white;
      border-color: #dc2626;
    }}
    .pending {{
      color: #ca8a04;
      font-weight: 700;
    }}
    .applied {{
      color: #16a34a;
      font-weight: 700;
    }}
    .failed, .rejected {{
      color: #dc2626;
      font-weight: 700;
    }}
    ul.compact {{
      margin: 0;
      padding: 0 20px;
    }}
    @media (max-width: 860px) {{
      .app-shell {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        border-right: 0;
        border-bottom: 1px solid var(--border);
        padding: 20px 16px;
      }}
      .main-content {{
        padding: 24px 16px 48px;
      }}
      .nav,
      .side-nav {{
        display: flex;
        flex-wrap: wrap;
      }}
      .nav-link,
      .side-link {{
        width: fit-content;
      }}
      .mode-grid {{
        grid-template-columns: 1fr;
      }}
      .kv-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-title">Workspace Terminal Bridge</div>
        <div class="brand-subtitle">Local MCP review panel</div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-label">Main</div>
        {primary_nav_html(active_nav)}
      </div>
      {f'<div class="sidebar-section"><div class="sidebar-label">Management</div>{management_nav_html(server_tab)}</div>' if server_tab else ''}
    </aside>
    <main class="main-content">
      <div class="content-inner">
        <div class="page-header">
          <h1>{escape(title)}</h1>
          {f'<p class="meta">{escape(subtitle)}</p>' if subtitle else ''}
        </div>
        {body}
      </div>
    </main>
  </div>
</body>
</html>
"""
    return html_text.encode("utf-8")


def page(title: str, body: str, active_nav: str = "", subtitle: str = "", server_tab: str | None = None) -> bytes:
    return app_shell(title, body, active_nav=active_nav, subtitle=subtitle, server_tab=server_tab)

