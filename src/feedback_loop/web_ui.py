"""Feedback Web UI — FastAPI server for researcher feedback.

Provides a web interface for:
1. Viewing pipeline outputs (skeleton, argument, figures, discussion)
2. Rating each stage (1-5)
3. Correcting specific fields
4. Viewing feedback history and pipeline improvement over time

Run: uvicorn src.feedback_loop.web_ui:app --port 8501
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Deep Paper Reader — Feedback UI", version="0.1.0")

DB_PATH = Path("./feedback_logs/feedback.db")


# ─── Database ───────────────────────────────────────────────────

def _init_db():
    """Initialize SQLite database for feedback storage."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            component TEXT DEFAULT '',
            target_id TEXT DEFAULT '',
            score INTEGER DEFAULT 3,
            feedback_type TEXT DEFAULT 'rating',
            field_name TEXT DEFAULT '',
            expected_value TEXT DEFAULT '',
            actual_value TEXT DEFAULT '',
            comment TEXT DEFAULT '',
            triggered_rerun INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT UNIQUE NOT NULL,
            title TEXT DEFAULT '',
            result_path TEXT DEFAULT '',
            processed_at TEXT DEFAULT '',
            overall_score REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def _get_db():
    return sqlite3.connect(str(DB_PATH))


# ─── API Models ─────────────────────────────────────────────────

class FeedbackSubmission(BaseModel):
    paper_id: str
    stage: str  # stage1, stage2, stage3, stage4
    component: str = ""
    target_id: str = ""  # e.g., "H1", "Fig2a"
    score: int = 3  # 1-5
    feedback_type: str = "rating"  # rating, correction, comment
    field_name: str = ""
    expected_value: str = ""
    actual_value: str = ""
    comment: str = ""


class PaperRegistration(BaseModel):
    paper_id: str
    title: str
    result_path: str


# ─── API Routes ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Main dashboard."""
    return _render_dashboard()


@app.get("/api/papers")
async def list_papers():
    """List all processed papers."""
    conn = _get_db()
    cursor = conn.execute(
        "SELECT paper_id, title, processed_at, overall_score FROM papers ORDER BY processed_at DESC"
    )
    papers = [
        {
            "paper_id": row[0],
            "title": row[1],
            "processed_at": row[2],
            "overall_score": row[3],
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return papers


@app.post("/api/papers")
async def register_paper(paper: PaperRegistration):
    """Register a processed paper."""
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO papers (paper_id, title, result_path, processed_at) VALUES (?, ?, ?, ?)",
            (paper.paper_id, paper.title, paper.result_path, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok"}


@app.get("/api/papers/{paper_id}/result")
async def get_paper_result(paper_id: str):
    """Get the pipeline result for a paper."""
    conn = _get_db()
    cursor = conn.execute("SELECT result_path FROM papers WHERE paper_id = ?", (paper_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(404, "Paper not found")

    result_path = Path(row[0])
    if not result_path.exists():
        raise HTTPException(404, f"Result file not found: {result_path}")

    import yaml
    with open(result_path) as f:
        return yaml.safe_load(f)


@app.post("/api/feedback")
async def submit_feedback(fb: FeedbackSubmission):
    """Submit feedback for a pipeline output."""
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO feedback 
               (timestamp, paper_id, stage, component, target_id, score, 
                feedback_type, field_name, expected_value, actual_value, comment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                fb.paper_id, fb.stage, fb.component, fb.target_id,
                fb.score, fb.feedback_type, fb.field_name,
                fb.expected_value, fb.actual_value, fb.comment,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": "Feedback recorded"}


@app.get("/api/feedback/{paper_id}")
async def get_feedback(paper_id: str):
    """Get all feedback for a paper."""
    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM feedback WHERE paper_id = ? ORDER BY timestamp DESC",
        (paper_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/stats")
async def get_stats():
    """Get aggregate feedback statistics."""
    conn = _get_db()

    # Average score by stage
    cursor = conn.execute(
        "SELECT stage, AVG(score) as avg_score, COUNT(*) as count "
        "FROM feedback WHERE feedback_type = 'rating' "
        "GROUP BY stage"
    )
    stage_stats = [
        {"stage": row[0], "avg_score": round(row[1], 2), "count": row[2]}
        for row in cursor.fetchall()
    ]

    # Recent trend (last 20 feedbacks)
    cursor = conn.execute(
        "SELECT timestamp, stage, score FROM feedback "
        "WHERE feedback_type = 'rating' "
        "ORDER BY timestamp DESC LIMIT 20"
    )
    recent = [
        {"timestamp": row[0], "stage": row[1], "score": row[2]}
        for row in cursor.fetchall()
    ]

    # Total papers
    cursor = conn.execute("SELECT COUNT(*) FROM papers")
    total_papers = cursor.fetchone()[0]

    # Total feedbacks
    cursor = conn.execute("SELECT COUNT(*) FROM feedback")
    total_feedbacks = cursor.fetchone()[0]

    conn.close()

    return {
        "total_papers": total_papers,
        "total_feedbacks": total_feedbacks,
        "stage_stats": stage_stats,
        "recent_trend": recent,
    }


@app.get("/paper/{paper_id}", response_class=HTMLResponse)
async def paper_detail(paper_id: str):
    """Paper detail view with feedback forms."""
    return _render_paper_page(paper_id)


# ─── HTML Templates ─────────────────────────────────────────────

def _render_dashboard() -> str:
    return """<!DOCTYPE html>
<html><head>
<title>Deep Paper Reader — Feedback</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f8f9fa; }
  h1 { color: #1a1a2e; }
  .card { background: white; border-radius: 8px; padding: 20px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .score { font-size: 1.5em; font-weight: bold; }
  .score.high { color: #2ecc71; } .score.mid { color: #f39c12; } .score.low { color: #e74c3c; }
  a { color: #3498db; text-decoration: none; } a:hover { text-decoration: underline; }
  table { width: 100%; border-collapse: collapse; } th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
  .btn { background: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
  .btn:hover { background: #2980b9; }
  #stats { display: flex; gap: 16px; flex-wrap: wrap; }
  .stat-box { flex: 1; min-width: 120px; text-align: center; }
</style>
</head><body>
<h1>🔬 Deep Paper Reader</h1>
<p>Feedback Dashboard — Rate and correct pipeline outputs</p>

<div id="stats" class="card">Loading stats...</div>

<div class="card">
  <h2>Processed Papers</h2>
  <div id="papers">Loading...</div>
</div>

<script>
async function load() {
  const stats = await (await fetch('/api/stats')).json();
  document.getElementById('stats').innerHTML = `
    <div class="stat-box"><div class="score">${stats.total_papers}</div><div>Papers</div></div>
    <div class="stat-box"><div class="score">${stats.total_feedbacks}</div><div>Feedbacks</div></div>
    ${stats.stage_stats.map(s => `
      <div class="stat-box">
        <div class="score ${s.avg_score >= 4 ? 'high' : s.avg_score >= 3 ? 'mid' : 'low'}">${s.avg_score}</div>
        <div>${s.stage}</div>
      </div>
    `).join('')}
  `;

  const papers = await (await fetch('/api/papers')).json();
  if (papers.length === 0) {
    document.getElementById('papers').innerHTML = '<p>No papers processed yet. Run the pipeline first.</p>';
    return;
  }
  document.getElementById('papers').innerHTML = `
    <table>
      <tr><th>Title</th><th>Score</th><th>Processed</th><th></th></tr>
      ${papers.map(p => `
        <tr>
          <td>${p.title || p.paper_id}</td>
          <td class="score ${p.overall_score >= 4 ? 'high' : p.overall_score >= 3 ? 'mid' : 'low'}">${p.overall_score || '—'}</td>
          <td>${p.processed_at ? new Date(p.processed_at).toLocaleDateString() : '—'}</td>
          <td><a href="/paper/${p.paper_id}" class="btn">Review</a></td>
        </tr>
      `).join('')}
    </table>
  `;
}
load();
</script>
</body></html>"""


def _render_paper_page(paper_id: str) -> str:
    return f"""<!DOCTYPE html>
<html><head>
<title>Review — {paper_id}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f8f9fa; }}
  .card {{ background: white; border-radius: 8px; padding: 20px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stage-header {{ cursor: pointer; display: flex; justify-content: space-between; align-items: center; }}
  .stage-content {{ display: none; margin-top: 12px; }}
  .stage-content.open {{ display: block; }}
  pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; }}
  .rating {{ display: flex; gap: 8px; margin: 8px 0; }}
  .rating button {{ width: 40px; height: 40px; border: 2px solid #ddd; border-radius: 50%; background: white; cursor: pointer; font-size: 1.1em; }}
  .rating button.selected {{ background: #3498db; color: white; border-color: #3498db; }}
  .rating button:hover {{ border-color: #3498db; }}
  textarea {{ width: 100%; height: 80px; border: 1px solid #ddd; border-radius: 4px; padding: 8px; font-family: inherit; }}
  .btn {{ background: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }}
  .btn:hover {{ background: #2980b9; }}
  .btn-green {{ background: #2ecc71; }} .btn-green:hover {{ background: #27ae60; }}
  .feedback-form {{ border-top: 1px solid #eee; padding-top: 12px; margin-top: 12px; }}
  a {{ color: #3498db; }}
</style>
</head><body>
<p><a href="/">← Dashboard</a></p>
<h1>📄 Paper Review</h1>
<p>Paper ID: <code>{paper_id}</code></p>

<div id="result">Loading pipeline result...</div>
<div id="feedback-history" class="card" style="display:none">
  <h3>Feedback History</h3>
  <div id="history-content"></div>
</div>

<script>
const paperId = "{paper_id}";
let resultData = null;

async function load() {{
  try {{
    resultData = await (await fetch(`/api/papers/${{paperId}}/result`)).json();
    renderResult(resultData);
  }} catch(e) {{
    document.getElementById('result').innerHTML = '<div class="card"><p>Could not load result. Process this paper first.</p></div>';
  }}

  try {{
    const feedback = await (await fetch(`/api/feedback/${{paperId}}`)).json();
    if (feedback.length > 0) {{
      document.getElementById('feedback-history').style.display = 'block';
      document.getElementById('history-content').innerHTML = feedback.map(f =>
        `<p><b>${{f.stage}}</b> — Score: ${{f.score}}/5 ${{f.comment ? '— ' + f.comment : ''}}</p>`
      ).join('');
    }}
  }} catch(e) {{}}
}}

function renderResult(data) {{
  const stages = [
    {{ key: 'skeleton', label: 'Stage 1: Skeleton Scan', data: data.skeleton }},
    {{ key: 'argument', label: 'Stage 2: Argument Extraction', data: data.argument }},
    {{ key: 'figures', label: 'Stage 3: Figure Interpretation', data: data.figures }},
    {{ key: 'discussion', label: 'Stage 4: Discussion Analysis', data: data.discussion }},
  ];

  document.getElementById('result').innerHTML = stages.map(s => `
    <div class="card">
      <div class="stage-header" onclick="this.nextElementSibling.classList.toggle('open')">
        <h3>${{s.label}}</h3>
        <span>▼</span>
      </div>
      <div class="stage-content">
        <pre>${{JSON.stringify(s.data, null, 2).slice(0, 3000)}}</pre>
        <div class="feedback-form">
          <h4>Rate this stage</h4>
          <div class="rating" id="rating-${{s.key}}">
            ${{[1,2,3,4,5].map(n => `<button onclick="selectRating('${{s.key}}', ${{n}})">${{n}}</button>`).join('')}}
          </div>
          <textarea id="comment-${{s.key}}" placeholder="Optional: corrections or comments..."></textarea>
          <br><br>
          <button class="btn btn-green" onclick="submitFeedback('${{s.key}}')">Submit Feedback</button>
        </div>
      </div>
    </div>
  `).join('');
}}

const ratings = {{}};
function selectRating(stage, score) {{
  ratings[stage] = score;
  document.querySelectorAll(`#rating-${{stage}} button`).forEach((btn, i) => {{
    btn.classList.toggle('selected', i + 1 === score);
  }});
}}

async function submitFeedback(stage) {{
  const score = ratings[stage] || 3;
  const comment = document.getElementById(`comment-${{stage}}`).value;
  await fetch('/api/feedback', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{
      paper_id: paperId,
      stage: stage,
      score: score,
      feedback_type: comment ? 'comment' : 'rating',
      comment: comment,
    }})
  }});
  alert(`Feedback submitted: ${{stage}} → ${{score}}/5`);
}}

load();
</script>
</body></html>"""
