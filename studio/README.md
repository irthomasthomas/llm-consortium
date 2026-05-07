# LLM Consortium Studio

A real-time React dashboard for orchestrating and visualizing multi-model LLM consortium runs.

## Architecture

- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Radix + Tailwind
- **Backend**: FastAPI Python server using the `llm_consortium` Python API directly
- **Database**: SQLite via `llm_consortium.db` module

## Quick Start


Open http://localhost:5173

## API Endpoints

- `GET /api/models` — Available LLM models
- `GET /api/consortiums` — Saved consortium configs
- `POST /api/consortiums/save` — Save new consortium
- `POST /api/consortiums/delete` — Delete consortium
- `POST /api/consortiums/run` — Run consortium (SSE streaming)
- `GET /api/runs` — Run history
- `GET /api/runs/{id}` — Run detail with members & decisions
- `GET /api/runs/{id}/stream` — SSE stream for active run
- `GET /api/strategies` — Available strategies
