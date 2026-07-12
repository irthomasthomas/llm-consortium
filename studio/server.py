#!/usr/bin/env python3
"""
LLM Consortium Dashboard — Novel frontend
Self-contained: Python stdlib only for the server.
Serves a beautiful dark-themed dashboard with live consortium data.
"""
import json, sqlite3, subprocess, os, sys, time, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

DB_PATH = Path.home() / ".config" / "io.datasette.llm" / "consortium_logs.db"
ROUTING_RULES = Path.home() / ".config" / "io.datasette.llm" / "routing_rules.json"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8888

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

class ConsortiumAPI:
    @staticmethod
    def stats():
        db = get_db()
        try:
            runs = db.execute("SELECT COUNT(*) FROM consortium_runs").fetchone()[0]
            members = db.execute("SELECT COUNT(*) FROM consortium_members").fetchone()[0]
            decisions = db.execute("SELECT COUNT(*) FROM arbiter_decisions").fetchone()[0]
            configs = db.execute("SELECT COUNT(*) FROM consortium_configs").fetchone()[0]
            embeddings = db.execute("SELECT COUNT(*) FROM response_embeddings").fetchone()[0]
        except:
            runs = members = decisions = configs = embeddings = 0
        db.close()
        return {"runs": runs, "members": members, "decisions": decisions,
                "configs": configs, "embeddings": embeddings}

    @staticmethod
    def recent_runs(limit=50):
        db = get_db()
        runs = db.execute("""
            SELECT cr.id, cr.created_at, cr.strategy, cr.status, cr.user_prompt,
                   cr.final_confidence, cr.iteration_count, cr.category,
                   (SELECT COUNT(*) FROM consortium_members cm WHERE cm.run_id = cr.id) as model_count,
                   (SELECT AVG(ad.confidence) FROM arbiter_decisions ad WHERE ad.run_id = cr.id) as avg_conf
            FROM consortium_runs cr
            ORDER BY cr.created_at DESC LIMIT ?
        """, [limit]).fetchall()
        db.close()
        return [dict(r) for r in runs]

    @staticmethod
    def model_leaderboard():
        db = get_db()
        try:
            rows = db.execute("""
                SELECT cm.role as model,
                       COUNT(*) as appearances,
                       SUM(CASE WHEN cm.response_id = ad.chosen_response_id THEN 1 ELSE 0 END) as wins
                FROM consortium_members cm
                JOIN arbiter_decisions ad ON ad.run_id = cm.run_id
                WHERE ad.chosen_response_id IS NOT NULL
                  AND cm.role NOT IN ('arbiter','dummy','member','healer-alpha','hunter-alpha')
                GROUP BY cm.role
                HAVING appearances >= 5
                ORDER BY wins DESC, appearances DESC
                LIMIT 30
            """).fetchall()
        except:
            rows = []
        db.close()
        results = []
        for r in rows:
            d = dict(r)
            d['win_rate'] = round(d['wins'] / d['appearances'] * 100, 1) if d['appearances'] > 0 else 0
            results.append(d)
        return results

    @staticmethod
    def configs(search="", limit=100):
        db = get_db()
        if search:
            rows = db.execute("""
                SELECT name, config, created_at FROM consortium_configs
                WHERE name LIKE ? ORDER BY created_at DESC LIMIT ?
            """, [f"%{search}%", limit]).fetchall()
        else:
            rows = db.execute("""
                SELECT name, config, created_at FROM consortium_configs
                ORDER BY created_at DESC LIMIT ?
            """, [limit]).fetchall()
        db.close()
        results = []
        for r in rows:
            d = dict(r)
            try:
                cfg = json.loads(d['config'])
                d['models'] = list(cfg.get('models', {}).keys())
                d['arbiter'] = cfg.get('arbiter', 'N/A')
                d['strategy'] = cfg.get('strategy', 'default')
            except:
                d['models'] = []
                d['arbiter'] = 'N/A'
                d['strategy'] = 'default'
            results.append(d)
        return results

    @staticmethod
    def routing_rules():
        if ROUTING_RULES.exists():
            return json.loads(ROUTING_RULES.read_text())
        return {}

    @staticmethod
    def run_detail(run_id):
        db = get_db()
        run = db.execute("SELECT * FROM consortium_runs WHERE id = ?", [run_id]).fetchone()
        members = db.execute("""
            SELECT cm.role, cm.response_id, cm.iteration,
                   r.response as text, r.model, r.duration_ms,
                   r.input_tokens, r.output_tokens
            FROM consortium_members cm
            LEFT JOIN responses r ON r.id = cm.response_id
            WHERE cm.run_id = ?
            ORDER BY cm.iteration, cm.member_index
        """, [run_id]).fetchall()
        decisions = db.execute("""
            SELECT * FROM arbiter_decisions WHERE run_id = ?
            ORDER BY iteration
        """, [run_id]).fetchall()
        db.close()
        return {
            "run": dict(run) if run else None,
            "members": [dict(m) for m in members],
            "decisions": [dict(d) for d in decisions]
        }

    @staticmethod
    def execute_prompt(model, prompt):
        """Run a consortium model via subprocess"""
        try:
            result = subprocess.run(
                ["llm", "-m", model, prompt],
                capture_output=True, text=True, timeout=120
            )
            return {"output": result.stdout[:5000], "error": result.stderr[:500] if result.stderr else None,
                    "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"output": "", "error": "Timeout after 120s", "returncode": -1}
        except Exception as e:
            return {"output": "", "error": str(e), "returncode": -1}

print("Part 1 written")

DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Consortium Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {
  --bg: #0a0a0f; --surface: #12121a; --surface2: #1a1a25; --border: #2a2a3a;
  --text: #e4e4ef; --muted: #8888a0; --accent: #6366f1; --accent2: #8b5cf6;
  --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6;
  --radius: 12px; --shadow: 0 4px 24px rgba(0,0,0,0.4);
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--text); min-height: 100vh; }
.header { background: linear-gradient(135deg, var(--surface), var(--surface2)); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 16px; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(12px); }
.header h1 { font-size: 20px; font-weight: 600; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header .badge { background: var(--accent); color: white; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.nav { display: flex; gap: 4px; margin-left: auto; }
.nav button { background: transparent; border: 1px solid transparent; color: var(--muted); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; transition: all .2s; font-family: inherit; }
.nav button:hover { background: var(--surface2); color: var(--text); }
.nav button.active { background: var(--accent); color: white; border-color: var(--accent); }
.container { max-width: 1400px; margin: 0 auto; padding: 24px; }
.grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; transition: transform .2s, box-shadow .2s; }
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--shadow); }
.stat-card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
.stat-card .value { font-size: 32px; font-weight: 700; margin-top: 4px; }
.stat-card .icon { float: right; opacity: 0.3; font-size: 28px; }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 24px; overflow: hidden; }
.panel-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.panel-header h2 { font-size: 15px; font-weight: 600; }
.panel-body { padding: 0; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 16px; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
td { padding: 10px 16px; border-bottom: 1px solid var(--border); font-size: 13px; }
tr:hover { background: var(--surface2); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.tag-success { background: rgba(16,185,129,.15); color: var(--green); }
.tag-fail { background: rgba(239,68,68,.15); color: var(--red); }
.tag-strategy { background: rgba(99,102,241,.15); color: var(--accent); }
.bar { display: inline-block; height: 6px; border-radius: 3px; background: var(--accent); vertical-align: middle; }
.bar-bg { display: inline-block; width: 100px; height: 6px; border-radius: 3px; background: var(--border); vertical-align: middle; margin-right: 8px; }
.input { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 13px; width: 100%; font-family: inherit; }
.input:focus { outline: none; border-color: var(--accent); }
.btn { background: var(--accent); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; transition: all .2s; font-family: inherit; }
.btn:hover { background: var(--accent2); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.console-output { background: #000; border-radius: 8px; padding: 16px; font-family: 'SF Mono', monospace; font-size: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: #0f0; border: 1px solid var(--border); }
.search-box { display: flex; gap: 8px; margin-bottom: 16px; }
.chart-container { padding: 20px; position: relative; height: 300px; }
.hidden { display: none !important; }
.loading { display: flex; align-items: center; justify-content: center; padding: 40px; color: var(--muted); }
.spinner { width: 24px; height: 24px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }
.fade-in { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.truncate { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.model-badge { display: inline-block; background: var(--surface2); border: 1px solid var(--border); padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
.confidence-ring { width: 36px; height: 36px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
</style>
</head>
<body>
<div class="header">
  <h1>🧠 Consortium</h1>
  <span class="badge" id="liveStatus">●</span>
  <nav class="nav">
    <button class="nav-btn active" data-view="dashboard">Dashboard</button>
    <button class="nav-btn" data-view="arena">Model Arena</button>
    <button class="nav-btn" data-view="console">Live Console</button>
    <button class="nav-btn" data-view="configs">Configs</button>
    <button class="nav-btn" data-view="routing">Routing Rules</button>
  </nav>
</div>
<div class="container">
  <!-- DASHBOARD VIEW -->
  <div id="view-dashboard" class="view fade-in">
    <div class="grid-stats" id="statsGrid"></div>
    <div class="panel">
      <div class="panel-header"><h2>📊 Recent Battles</h2><span id="runsCount" style="color:var(--muted);font-size:12px"></span></div>
      <div class="panel-body">
        <table>
          <thead><tr><th>Time</th><th>Strategy</th><th>Models</th><th>Iters</th><th>Confidence</th><th>Prompt</th><th>Status</th></tr></thead>
          <tbody id="runsTable"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ARENA VIEW -->
  <div id="view-arena" class="view hidden">
    <div class="panel">
      <div class="panel-header"><h2>🏆 Model Leaderboard</h2><span style="color:var(--muted);font-size:12px">Min 5 appearances</span></div>
      <div class="panel-body">
        <table>
          <thead><tr><th>#</th><th>Model</th><th>Wins</th><th>Appearances</th><th>Win Rate</th><th>Performance</th></tr></thead>
          <tbody id="leaderboardTable"></tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>📈 Win Rate Distribution</h2></div>
      <div class="chart-container"><canvas id="winRateChart"></canvas></div>
    </div>
  </div>

  <!-- CONSOLE VIEW -->
  <div id="view-console" class="view hidden">
    <div class="panel">
      <div class="panel-header"><h2>⚡ Live Consortium Console</h2></div>
      <div style="padding:20px;">
        <div style="display:flex;gap:8px;margin-bottom:12px;">
          <select class="input" id="consoleModel" style="width:300px;">
            <option value="cns-oracle">cns-oracle</option>
            <option value="cns-zen-tg-overhaul">cns-zen-tg-overhaul</option>
          </select>
          <input class="input" id="consolePrompt" placeholder="Enter your prompt..." onkeydown="if(event.key==='Enter')runPrompt()">
          <button class="btn" id="runBtn" onclick="runPrompt()">Run ▶</button>
        </div>
        <div class="console-output" id="consoleOutput">Ready. Select a consortium model and enter a prompt.</div>
        <div id="consoleTimer" style="color:var(--muted);font-size:12px;margin-top:8px;"></div>
      </div>
    </div>
  </div>

  <!-- CONFIGS VIEW -->
  <div id="view-configs" class="view hidden">
    <div class="panel">
      <div class="panel-header"><h2>⚙️ Consortium Configurations</h2><span id="configCount" style="color:var(--muted);font-size:12px"></span></div>
      <div style="padding:16px;">
        <div class="search-box">
          <input class="input" id="configSearch" placeholder="Search configs..." onkeydown="if(event.key==='Enter')loadConfigs()">
          <button class="btn" onclick="loadConfigs()">Search</button>
        </div>
      </div>
      <div class="panel-body">
        <table>
          <thead><tr><th>Name</th><th>Models</th><th>Arbiter</th><th>Strategy</th><th>Created</th></tr></thead>
          <tbody id="configsTable"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ROUTING VIEW -->
  <div id="view-routing" class="view hidden">
    <div class="panel">
      <div class="panel-header"><h2>🧭 Routing Rules</h2></div>
      <div class="panel-body" id="routingContent" style="padding:20px;"></div>
    </div>
  </div>
</div>

<script>
const API = window.location.origin;
function fmt(s){ if(!s) return ''; if(s.length>50) return s.substring(0,50)+'...'; return s; }
function timeAgo(s){ if(!s) return '-'; const d=new Date(s+'Z'); const n=Date.now()-d.getTime(); const m=Math.floor(n/60000); if(m<1) return 'just now'; if(m<60) return m+'m ago'; const h=Math.floor(m/60); if(h<24) return h+'h ago'; return Math.floor(h/24)+'d ago'; }

async function api(path){ const r=await fetch(API+'/api/'+path); return r.json(); }

async function loadDashboard(){
  const stats = await api('stats');
  document.getElementById('statsGrid').innerHTML = `
    <div class="stat-card"><span class="icon">⚔️</span><div class="label">Total Battles</div><div class="value">${stats.runs||0}</div></div>
    <div class="stat-card"><span class="icon">🤖</span><div class="label">Model Entries</div><div class="value">${stats.members||0}</div></div>
    <div class="stat-card"><span class="icon">⚖️</span><div class="label">Arbiter Decisions</div><div class="value">${stats.decisions||0}</div></div>
    <div class="stat-card"><span class="icon">⚙️</span><div class="label">Saved Configs</div><div class="value">${stats.configs||0}</div></div>
    <div class="stat-card"><span class="icon">📐</span><div class="label">Embeddings</div><div class="value">${stats.embeddings||0}</div></div>`;
  const runs = await api('runs?limit=50');
  document.getElementById('runsCount').textContent = `${runs.length} shown`;
  document.getElementById('runsTable').innerHTML = runs.map(r=>`
    <tr>
      <td style="white-space:nowrap">${timeAgo(r.created_at)}</td>
      <td><span class="tag tag-strategy">${r.strategy||'default'}</span></td>
      <td>${r.model_count||0}</td>
      <td>${r.iteration_count||0}</td>
      <td>${r.avg_conf?(r.avg_conf*100).toFixed(0)+'%':'-'}</td>
      <td class="truncate" title="${(r.user_prompt||'').replace(/"/g,'&quot;')}">${fmt(r.user_prompt)||'-'}</td>
      <td><span class="tag ${r.status==='success'?'tag-success':'tag-fail'}">${r.status||'?'}</span></td>
    </tr>`).join('') || '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--muted)">No runs found</td></tr>';
}

async function loadArena(){
  const data = await api('leaderboard');
  const maxApp = Math.max(...data.map(d=>d.appearances),1);
  document.getElementById('leaderboardTable').innerHTML = data.map((m,i)=>`
    <tr>
      <td style="font-weight:700;color:${i<3?'var(--accent)':'var(--muted)'}">${i+1}</td>
      <td style="font-weight:600">${m.model}</td>
      <td style="color:var(--green);font-weight:600">${m.wins}</td>
      <td>${m.appearances}</td>
      <td style="font-weight:700">${m.win_rate}%</td>
      <td><span class="bar-bg"><span class="bar" style="width:${m.win_rate}%"></span></span></td>
    </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--muted)">No data</td></tr>';
  const ctx = document.getElementById('winRateChart');
  if(window._chart) window._chart.destroy();
  window._chart = new Chart(ctx, {type:'bar',data:{labels:data.slice(0,15).map(d=>d.model.substring(0,20)),datasets:[{label:'Win %',data:data.slice(0,15).map(d=>d.win_rate),backgroundColor:'#6366f1',borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#8888a0',font:{size:10}},grid:{display:false}},y:{ticks:{color:'#8888a0'},grid:{color:'#2a2a3a'}}}}});
}

async function loadConfigs(){
  const search = document.getElementById('configSearch').value;
  const data = await api('configs'+(search?('?search='+encodeURIComponent(search)):''));
  document.getElementById('configCount').textContent = `${data.length} configs`;
  document.getElementById('configsTable').innerHTML = data.map(c=>`
    <tr>
      <td style="font-weight:600">${c.name}</td>
      <td>${(c.models||[]).map(m=>`<span class="model-badge">${m}</span>`).join('')}</td>
      <td style="color:var(--accent)">${c.arbiter||'-'}</td>
      <td><span class="tag tag-strategy">${c.strategy||'default'}</span></td>
      <td style="color:var(--muted)">${timeAgo(c.created_at)}</td>
    </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--muted)">No configs</td></tr>';
}

async function loadRouting(){
  const rules = await api('routing');
  let html = '';
  for(const [cat, data] of Object.entries(rules)){
    const models = (data.models||[]).map(m=>`<span class="model-badge">${m}</span>`).join('');
    html += `<div style="margin-bottom:16px;padding:16px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span class="tag tag-strategy" style="text-transform:uppercase">${cat}</span>
        <span style="color:var(--muted);font-size:12px">→ ${data.strategy||'pick_best'}</span>
      </div>
      <div>${models}</div></div>`;
  }
  document.getElementById('routingContent').innerHTML = html || '<p style="color:var(--muted)">No routing rules found</p>';
}

async function runPrompt(){
  const model = document.getElementById('consoleModel').value;
  const prompt = document.getElementById('consolePrompt').value;
  if(!prompt) return;
  const btn = document.getElementById('runBtn');
  btn.disabled = true; btn.textContent = 'Running...';
  document.getElementById('consoleOutput').textContent = `Running ${model}...\n`;
  const start = Date.now();
  try {
    const r = await fetch(API+'/api/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,prompt})});
    const data = await r.json();
    const elapsed = ((Date.now()-start)/1000).toFixed(1);
    let txt = data.output || '(no output)';
    if(data.error) txt += '\n\n--- ERROR ---\n' + data.error;
    txt += `\n\n--- Completed in ${elapsed}s ---`;
    document.getElementById('consoleOutput').textContent = txt;
    document.getElementById('consoleTimer').textContent = `⏱ ${elapsed}s | exit: ${data.returncode}`;
  } catch(e) {
    document.getElementById('consoleOutput').textContent = 'Error: ' + e.message;
  }
  btn.disabled = false; btn.textContent = 'Run ▶';
}

// Navigation
document.querySelectorAll('.nav-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v=>v.classList.add('hidden'));
    const view = btn.dataset.view;
    document.getElementById('view-'+view).classList.remove('hidden');
    document.getElementById('view-'+view).classList.add('fade-in');
    if(view==='dashboard') loadDashboard();
    if(view==='arena') loadArena();
    if(view==='configs') loadConfigs();
    if(view==='routing') loadRouting();
  });
});

// Init
loadDashboard();
setInterval(()=>{ const el=document.getElementById('liveStatus'); el.style.opacity = el.style.opacity==='0.3'?'1':'0.3'; }, 1500);
</script>
</body>
</html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == '/' or path == '/index.html':
            self._html(DASHBOARD_HTML)
        elif path.startswith('/api/'):
            self._api(path[5:], qs)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/execute':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            result = ConsortiumAPI.execute_prompt(body.get('model',''), body.get('prompt',''))
            self._json(result)
        else:
            self._json({"error": "not found"}, 404)

    def _api(self, endpoint, qs):
        try:
            if endpoint == 'stats':
                self._json(ConsortiumAPI.stats())
            elif endpoint == 'runs':
                self._json(ConsortiumAPI.recent_runs(int(qs.get('limit',['50'])[0])))
            elif endpoint == 'leaderboard':
                self._json(ConsortiumAPI.model_leaderboard())
            elif endpoint == 'configs':
                search = qs.get('search',[''])[0]
                self._json(ConsortiumAPI.configs(search))
            elif endpoint == 'routing':
                self._json(ConsortiumAPI.routing_rules())
            elif endpoint.startswith('run/'):
                self._json(ConsortiumAPI.run_detail(endpoint.split('/')[1]))
            else:
                self._json({"error": f"unknown endpoint: {endpoint}"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _html(self, content, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == '__main__':
    print(f"🧠 Consortium Dashboard → http://localhost:{PORT}")
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down")
        server.server_close()
