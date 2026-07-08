# Agent-Aware Pro

> A **production-architecture rebuild** of the multi-platform search & comparison idea from [agent-aware](https://github.com/vedhakoushik/agent-aware) — done right.

**The one inversion that changes everything:** the LLM is the **reasoning** layer (understand the query, rank, explain), **not** the **data** layer. Data comes from **structured supplier APIs** (Amadeus, SerpApi, …) — *never* real-time LLM scraping. That single change makes it **fast, reliable, and hallucination-proof**.

> **Status — working professional spine, not a finished product.** The architecture is real and runs today on realistic **demo data** out of the box; add API keys to flip individual connectors to **live**. It is intentionally the *reliable core* — booking, auth, and price prediction are deliberately out of scope (see **[Known Limitations](#known-limitations)**).

---

## Why it exists

The [student build](https://github.com/vedhakoushik/agent-aware) proved the *idea* is great but that **real-time, LLM-driven scraping is the fragile part** — travel sites bot-block, free LLM tiers rate-limit, and browser agents are slow. This rebuild keeps the good ideas and removes the fragile foundation.

| | agent-aware (student) | **agent-aware-pro** |
|---|---|---|
| **Data source** | LLM scrapes sites live | **Structured supplier APIs** |
| **Speed** | 60–180s, browser agents | **sub-second (cached) / few s** |
| **Hallucination** | can invent results | **structurally impossible** — the winner must cite a real offer id |
| **Reliability** | breaks on any site change | **stable API contracts** |
| **Architecture** | one Streamlit process | **decoupled FastAPI + streaming UI** |

## Architecture

```
Client (streaming UI)
   ↓
FastAPI / BFF          async jobs · SSE streaming
   ↓
Intelligence (LLM)     intent understanding · grounded ranking + explanation
   ↓
Orchestration          parallel supplier fan-out · per-source timeout · normalize → one schema
   ↓
Data connectors        Amadeus / SerpApi · hotel APIs   (each LIVE with a key, DEMO without)
   ↓
Suppliers (external)
   + cross-cutting:     cache (Redis or in-memory) · observability hooks
```

Every supplier is normalized into **one canonical `Offer` schema** (`backend/schema.py`), so ranking, the UI, and the LLM all speak one language. **Adding a supplier = adding one connector.**

**Grounding guarantee:** the recommendation's `winner_id` *must* be the id of a real offer that came back from a connector, so the LLM cannot fabricate a result — it can only pick and explain among real ones (`backend/reasoning.py`), with a deterministic cheapest-option fallback.

## Run it

Works immediately on realistic **demo data** — no keys required.

```bash
cd agent-aware-pro
python run.py
```

Open **http://localhost:8000**.

> The included run reuses the sibling `agent-aware/.venv` if present; otherwise `pip install -r requirements.txt` first.

## Go live (optional)

Add keys to `.env` to flip a connector from demo → live:

| Key | Flips on | Get it at |
|---|---|---|
| `SERPAPI_KEY` | real product prices (Google Shopping) + Google Flights | https://serpapi.com |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | real flight offers | https://developers.amadeus.com |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | LLM reasoning (Ollama works fully offline as failover) | console.groq.com · aistudio.google.com |
| `REDIS_URL` | shared cache (blank = in-process) | — |

No LLM key is required to try it — Groq → Gemini → local Ollama failover is already wired.

## Known limitations

Being transparent about what this core does **not** yet do:

- **Hotels are still demo-only.** Flights + products go live with keys; the hotel connector returns demo data (Google Hotels via the same SerpApi key is the intended next add).
- **No booking or checkout.** It finds, compares, and recommends — it does not transact.
- **No user auth.** Google OAuth is scaffolded but not wired (needs you to create a Google OAuth client); there are no user accounts or saved history yet.
- **No conversational refine / price prediction.** Each search is stateless; follow-up refinement and forecasting are future work.
- **Light test coverage.** The reasoning grounding is deterministic and easy to trust, but this rebuild does not yet carry the test suite the [capstone project](https://github.com/vedhakoushik/placement-prep-agent) does.

## License

[MIT](LICENSE) — built for learning. Use freely.
