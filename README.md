# cascAIde

cascAIde is a dependency transplant engine for vulnerable packages. It scans a public GitHub repository, builds a dependency and call-site graph, opens a mock CVE incident, and runs an assisted rewrite pipeline that can replace risky dependency usage with safer native code.

The current demo focuses on migrating `axios` call sites to a behavior-preserving `fetch` wrapper, then validating the patch through build/test checks, behavioral comparison, and a multi-judge review flow.

## What It Does

- Scans public repositories for vulnerable dependency usage.
- Builds an impact graph that connects packages, files, imports, aliases, and call sites.
- Highlights aliased call sites that simple grep-style checks can miss.
- Generates mitigation options for an incident.
- Runs an autonomous transplant pipeline for dependency replacement.
- Verifies generated patches with sandboxed build/test/behavior checks.
- Presents diff review, judge verdicts, and approval flow in a React UI.

## Architecture

```text
frontend/                 React + Vite UI
backend/main.py           FastAPI app and HTTP/SSE routes
backend/container.py      Runtime dependency wiring
backend/domain/           Core models, enums, errors, deterministic helpers
backend/services/         Scanning, planning, rewriting, judging, verification
backend/adapters/fake/    In-memory/demo adapters
backend/adapters/live/    Live integrations for external systems
backend/ports/            Interface contracts for adapters
backend/tests/            Unit tests for domain, ports, and services
```

## Tech Stack

- Python 3.14
- FastAPI
- Pydantic
- Server-Sent Events
- React 18
- TypeScript
- Vite

## Quick Start

### Backend

```bash
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.main:app --reload --app-dir ..
```

By default, the backend runs with fake/demo services enabled, so the app can be explored without live infrastructure credentials.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The UI talks to the FastAPI backend and streams pipeline progress as the incident runs.

## Useful Commands

Run backend tests:

```bash
cd backend
pytest
```

Build the frontend:

```bash
cd frontend
npm run build
```

Serve the backend with the built frontend:

```bash
cd backend
uvicorn backend.main:app --app-dir ..
```

## Configuration

Configuration is read from environment variables with the `DEPCOVER_` prefix. The default mode uses fake adapters. Live mode can be enabled by setting:

```bash
DEPCOVER_USE_FAKES=false
```

When live mode is enabled, configure the required external services and LLM role variables in the environment before starting the backend.

## Demo Flow

1. Enter a public GitHub repository URL.
2. Scan the repo to build the dependency and call-site graph.
3. Fire a mock CVE incident.
4. Choose the transplant mitigation.
5. Watch the live pipeline stream through recall, rewrite, validation, verification, and judge stages.
6. Review the generated diff and final verdicts.

## Repository Note

The product planning document is intentionally not included in this public repository.
