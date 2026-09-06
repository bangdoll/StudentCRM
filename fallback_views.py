"""
後備降級頁面渲染視圖 (fallback_views.py)
========================================
當 Jinja2 模板遺失或處於唯讀無檔案系統環境時，提供純 HTML/CSS 的基礎看板與錯誤頁面。
"""

import os
from fastapi.responses import HTMLResponse


def template_exists(templates_dir: str, name: str) -> bool:
    return os.path.exists(os.path.join(templates_dir, name))


def use_fallback_pages(templates_dir: str, name: str) -> bool:
    return not template_exists(templates_dir, name)


def render_fallback_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Noto Sans TC", sans-serif; background: #f6f7f9; color: #18202a; }}
        header {{ padding: 28px 24px; background: #111827; color: white; }}
        main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
        a {{ color: #155eef; text-decoration: none; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
        .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
        .card strong {{ display: block; font-size: 28px; margin-top: 8px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
        th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #eef0f3; }}
        th {{ color: #5b6472; font-size: 13px; }}
        .muted {{ color: #6b7280; }}
        .nav {{ display: flex; gap: 16px; margin-top: 12px; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <nav class="nav">
            <a href="/dashboard">學員看板</a>
            <a href="/digital-management">數位管理教學</a>
            <a href="/program/apple-ceo">蘋果總裁班</a>
            <a href="/api/students">API</a>
        </nav>
    </header>
    <main>{body}</main>
</body>
</html>""")


def render_dashboard_fallback(students: list[dict], apple_summary: dict, sync_status: dict) -> HTMLResponse:
    rows = "\n".join(
        f"<tr><td>{student.get('name', '')}</td><td>{student.get('next_lesson') or '安排中'}</td><td>{student.get('lessons_count', 0)}</td><td>{student.get('latest_date') or '未記錄'}</td></tr>"
        for student in students[:80]
    )
    if not rows:
        rows = '<tr><td colspan="4" class="muted">尚未載入學員資料。請確認 Vercel 環境變數與 Supabase 匯入狀態。</td></tr>'

    body = f"""
    <section class="grid">
        <div class="card"><span>全部學員</span><strong>{len(students)}</strong></div>
        <div class="card"><span>續班提醒</span><strong>{apple_summary.get('completed_student_count', 0)}</strong></div>
        <div class="card"><span>場地餘額</span><strong>{apple_summary.get('latest_balance_label', '$0')}</strong></div>
        <div class="card"><span>同步引擎</span><strong style="font-size:20px">{sync_status.get('engine', 'unknown')}</strong></div>
    </section>
    <section class="card">
        <p class="muted">來源：{sync_status.get('source', '')}</p>
        <table>
            <thead><tr><th>學員</th><th>下次上課</th><th>累計堂數</th><th>最近上課</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </section>
    """
    return render_fallback_page("StudentCRM 學員行動看板", body)
