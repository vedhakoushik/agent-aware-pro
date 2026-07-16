# Changelog

All notable changes to agent-aware-pro are documented here.

## [Unreleased]

### Planned
- Live Amadeus flight connector (swap demo data for real API calls)
- SerpApi product search connector
- User-facing streaming UI (React + SSE)
- Auth layer (JWT, user sessions)

## [1.0.0] — 2026-07-08

### Added
- FastAPI backend with Server-Sent Events (SSE) streaming
- LLM reasoning layer: intent understanding, grounded ranking, natural-language explanation
- Amadeus connector (demo mode — returns realistic structured fixture data)
- SerpApi product connector (demo mode)
- Structured response contracts: every result links a real `offer_id`, hallucination structurally impossible
- `run.py` launcher — starts backend and frontend in one command
- `.env.example` with all required keys documented
- Architecture diagram in `README.md`
- Docker support (`Dockerfile`, `.dockerignore`)

### Architecture decisions
- **LLM = reasoning only.** Data always comes from supplier APIs, never LLM generation. This makes results verifiable and removes rate-limit risk from the hot path.
- **SSE over WebSockets.** Unidirectional streaming is sufficient for this use case; SSE is simpler to proxy and deploy.
- **Demo fixtures by default.** The app runs fully offline without any API keys, making local development and demos frictionless.

## [0.1.0] — 2026-07-07

### Added
- Initial project scaffold: FastAPI + frontend placeholder
- Decision to rebuild agent-aware on structured APIs instead of LLM scraping
