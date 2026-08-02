# Consortium Dashboard — Novel Frontend

A self-contained, zero-dependency web dashboard for the `llm-consortium` system.

## Quick Start

```bash
python3 studio/server.py [port]  # default: 8888
# Open http://localhost:8888
```

## Architecture

```
studio/server.py     # Single Python file (496 lines, stdlib only)
  ├── ConsortiumAPI  # Direct SQLite queries to consortium_logs.db
  ├── Dashboard HTML # Embedded dark-themed SPA (vanilla JS + Chart.js)
  └── HTTP Handler   # REST API + static HTML serving
```

**No build step. No npm. No React. No pip install.** Just Python 3.

## Views

### 1. Battle Dashboard
- Live stats: 1,105 runs, 7,050 model entries, 1,413 arbiter decisions
- Recent battles table: strategy, model count, iterations, confidence, prompt snippet, status
- Auto-refreshing

### 2. Model Arena
- Win-rate leaderboard from historical battle data
- Models with ≥5 appearances ranked by wins/appearances
- Bar chart visualization (Chart.js)
- Example: deepseek-v4-pro leads with 98 wins from 506 appearances (19.4%)

### 3. Live Console
- Submit prompts to any saved consortium model (`cns-oracle`, etc.)
- Real-time output with timing
- Uses `subprocess.run(["llm", "-m", model, prompt])`

### 4. Config Explorer
- Search 670 saved consortium configurations
- Shows models, arbiter, strategy for each config
- Full-text search across config names

### 5. Routing Rules
- Displays current `routing_rules.json`
- Category → models → strategy mapping
- Shows coding/math/reasoning/general routing

## Design

- **Theme**: Dark (Vercel/Linear aesthetic)
- **CSS**: Custom properties, CSS Grid, animations
- **JS**: Vanilla fetch API, no frameworks
- **Charts**: Chart.js from CDN
- **Typography**: SF Mono / Fira Code

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | Database statistics |
| `GET /api/runs?limit=N` | Recent consortium runs |
| `GET /api/leaderboard` | Model win-rate leaderboard |
| `GET /api/configs?search=X` | Saved configs (searchable) |
| `GET /api/routing` | Current routing rules |
| `GET /api/run/:id` | Detailed run trace |
| `POST /api/execute` | Execute consortium prompt |

## Data Source

Direct SQLite queries to `~/.config/io.datasette.llm/consortium_logs.db`:
- `consortium_runs` (1,105 rows)
- `consortium_members` (7,050 rows)
- `arbiter_decisions` (1,413 rows)
- `consortium_configs` (670 rows)
- `response_embeddings` (666 rows)

---

## React Studio (rich UI, optional)

The `feature/studio-backend` UI was merged into this repo as an optional richer
alternative. It uses React + TypeScript + Vite with shadcn/ui, and a FastAPI
backend at `studio/backend/server.py`.

```bash
cd studio
npm install
npm run dev            # frontend on :5173
python3 backend/server.py   # API backend (FastAPI)
```

Views: Studio, Compare, Analytics, History, Leaderboard, LiveEval. SSE live
streaming, direct Python API integration (no CLI subprocess). Excludes
consortium configs from the model list.

The zero-dependency dashboard above (`studio/server.py`) remains the default
when you just want a quick read-only view without any build step.
