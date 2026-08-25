# 🛡️ Brand Guardian AI

### AI compliance auditor for video advertisements

Brand Guardian AI watches a video ad so a compliance reviewer doesn't have to.
Give it a YouTube URL or upload a video file — it transcribes the speech,
OCRs every on-screen graphic, checks both against a knowledge base of
regulatory rules (FTC guidelines, CAP Code, or any rulebook you index
yourself), and returns a **PASS/FAIL verdict** where every flagged violation
must cite an exact quote from the transcript or on-screen text. No citation,
no violation — this kills hallucinated flags and stops puffery ("the best
you'll ever feel") from being mistaken for a compliance breach.

**Live app:** [brandgurdian.lol](https://brandgurdian.lol)
**API:** [api.brandgurdian.lol/docs](https://api.brandgurdian.lol/docs)

---

## What it can do

- **Audit by URL or by upload** — paste a YouTube link (server downloads it)
  or upload a video file directly, whichever fits your workflow.
- **Understands both audio and on-screen text** — speech-to-text transcript
  *and* OCR of graphics/lower-thirds/disclaimers, so a claim buried in
  on-screen fine print gets caught just as reliably as a spoken one.
- **Grounded in your own rulebook, not the model's memory** — upload
  compliance PDFs once (CAP Code, FTC guidance, an internal brand policy —
  anything) and every audit retrieves and cites the most relevant clauses
  from *those* documents via RAG, instead of GPT-4o guessing from general
  training knowledge.
- **Evidence-required verdicts** — the compliance prompt forces every
  flagged violation to quote the exact transcript/OCR text that triggered
  it, plus the specific rule it breaks. Tuned over real false positives to
  stop over-flagging marketing puffery and vague superlatives.
- **Built for long-running jobs** — video indexing takes minutes, so audits
  run as background jobs you poll for status, instead of holding an HTTP
  connection open until it times out.
- **Self-serve rule management** — swap out the entire compliance rulebook
  (clear + re-index) without touching code, via the same API/UI a
  non-engineer would use.

---

## Architecture

```
[YouTube URL]  OR  [Uploaded Video File]
        ↓
[Azure Video Indexer] → [Transcript + OCR Extraction]
        ↓
[Azure AI Search Vector DB] ← [OpenAI Embeddings RAG Retrieval]
   (Compliance PDFs indexed via /upload-rules)
        ↓
[GPT-4o Compliance Auditor] → [Structured Violation Report]
        ↓
[FastAPI Backend + Async Job Polling] ← [Static Frontend, served separately]
```

The API (`backend/`) and the frontend (`web/`) are fully decoupled — the API
is a pure JSON service with no HTML routes; the frontend is a separate
static site that calls it over `fetch()`. They can be hosted, scaled, and
versioned independently.

### Core Components

| Layer | Technology |
|---|---|
| Orchestration | LangGraph StateGraph (2-node DAG) |
| Video Processing | Azure Video Indexer (speech-to-text + OCR) |
| Knowledge Base | Azure AI Search (vector DB) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | OpenAI GPT-4o (temperature 0.0) |
| API | FastAPI + Uvicorn, async job polling |
| Frontend | Plain HTML/CSS/JS, no build step |
| Observability | LangSmith tracing + Azure Application Insights (optional) |
| Testing | pytest + FastAPI TestClient |
| Containerization | Docker |
| CI/CD | GitHub Actions → Docker Hub → SSH deploy |

### LangGraph Workflow

```
START → [index_video_node] → [audit_content_node] → END
```

**Node 1 — Video Indexer**
- Downloads the YouTube video via `yt-dlp`, *or* uses an already-uploaded
  local file — whichever the request provided.
- Uploads it to Azure Video Indexer, polls until processing completes,
  extracts the transcript and OCR text.

**Node 2 — Compliance Auditor**
- Embeds transcript + OCR text, retrieves the top-3 most relevant rules
  from Azure AI Search.
- Sends transcript, OCR, and retrieved rules to GPT-4o with a strict
  citation-required system prompt.
- Returns structured JSON: PASS/FAIL, violations with severity, and a
  plain-English summary.

---

## Getting Started

### Prerequisites

- Python 3.14 (see `.python-version` / `pyproject.toml`)
- [`uv`](https://docs.astral.sh/uv/) for local dependency management
- An OpenAI API key
- Azure resources: Video Indexer, AI Search, and a Service Principal
  (Tenant ID / Client ID / Client Secret) with the **Video Indexer Account
  Contributor** role assigned directly on the Video Indexer resource
- (Optional) LangSmith account for trace debugging

### Installation

```bash
git clone https://github.com/ShibjiRout/Brand-Guardian-AI.git
cd Brand-Guardian-AI
uv sync
```

### Environment Variables

Create a `.env` file in the project root:

```env
# OpenAI
OPENAI_API_KEY="sk-..."

# Azure AI Search
AZURE_SEARCH_ENDPOINT="https://your-search.search.windows.net"
AZURE_SEARCH_API_KEY="your-key"
AZURE_SEARCH_INDEX_NAME="brand-compliance-rules"

# Azure Video Indexer
AZURE_VI_NAME="your-vi-name"
AZURE_VI_LOCATION="eastus"
AZURE_VI_ACCOUNT_ID="your-account-id"
AZURE_SUBSCRIPTION_ID="your-subscription-id"
AZURE_RESOURCE_GROUP="your-resource-group"

# Azure Service Principal (Video Indexer auth — works on any host, not just Azure)
AZURE_TENANT_ID="your-tenant-id"
AZURE_CLIENT_ID="your-client-id"
AZURE_CLIENT_SECRET="your-client-secret"

# Optional — Application Insights
APPLICATIONINSIGHTS_CONNECTION_STRING=""

# Optional — LangSmith tracing
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY="lsv2_..."
LANGSMITH_PROJECT="Brand Guardian AI"
```

> Note: Docker's `--env-file` does **not** strip quotes the way
> `python-dotenv` does — if you ever load this file into a container
> directly, use unquoted values.

### Index Compliance Rules (PDF Upload)

Use the audit tool's **Step 1 panel** (`web/app.html`) to upload compliance
PDFs (CAP Code, FTC guidance, etc.) directly into Azure AI Search — no
scripts needed. Or standalone:

```bash
uv run python backend/scripts/index_documents.py path/to/rules.pdf
```

Or via API:

```bash
curl -X POST https://api.brandgurdian.lol/upload-rules \
  -F "files=@CAP-Code.pdf" \
  -F "clear_first=false"
```

To wipe the index and start fresh:

```bash
curl -X POST https://api.brandgurdian.lol/clear-rules
```

### Run Locally

The API and frontend are two separate processes:

```bash
# Terminal 1 — the API
uv run uvicorn backend.src.api.server:app --reload
```

```bash
# Terminal 2 — the frontend (static files, no build step)
cd web && python3 -m http.server 5500
```

- App: `http://localhost:5500/index.html`
- API docs: `http://localhost:8000/docs`

`web/app.html` calls `http://localhost:8000` automatically when running on
`localhost`; in production it points at `https://api.brandgurdian.lol`.

Quick graph-only smoke test, no API needed:

```bash
uv run python main.py
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Run with Docker (local)

```bash
docker compose up --build
curl http://localhost:8000/health
```

---

## Project Structure

```
brand-guardian-ai/
├── backend/
│   ├── scripts/
│   │   └── index_documents.py   # PDF chunking + Azure AI Search indexer (CLI + API)
│   └── src/
│       ├── api/
│       │   ├── server.py        # FastAPI app — pure JSON API, no frontend coupling
│       │   └── telemetry.py     # Azure Monitor / OpenTelemetry setup
│       ├── graph/
│       │   ├── state.py         # LangGraph state schema
│       │   ├── nodes.py         # Video Indexer + GPT-4o Auditor nodes
│       │   └── workflow.py      # LangGraph DAG definition
│       └── services/
│           └── video_indexer.py # Azure Video Indexer service (Service Principal auth)
├── web/
│   ├── index.html               # Landing page
│   ├── app.html                 # Audit tool UI (rule upload + video audit)
│   ├── theme.css                # Shared design tokens
│   └── theme.js                 # Light/dark theme toggle
├── tests/
│   └── test_smoke.py            # FastAPI TestClient smoke tests
├── main.py                      # CLI entry point (graph-only smoke test)
├── docker-compose.yml           # Local build/test convenience
├── Dockerfile
└── requirements.txt
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/audit` | Submit a YouTube URL — returns `job_id` immediately |
| `POST` | `/audit-upload` | Upload a video file + metadata — returns `job_id` immediately |
| `GET` | `/status/{job_id}` | Poll for audit job result |
| `POST` | `/upload-rules` | Upload PDF compliance rules into Azure AI Search |
| `POST` | `/clear-rules` | Delete all indexed compliance rules |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive Swagger UI |

### Async Job Flow

Audits run as background jobs to avoid gateway timeouts on long video
processing:

```bash
# 1. Submit an audit
curl -X POST https://api.brandgurdian.lol/audit \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://youtu.be/your-video-id"}'
# → {"job_id": "abc-123"}

# 2. Poll for the result
curl https://api.brandgurdian.lol/status/abc-123
# → {"status": "complete", "result": {...}}
```

### Example Result

```json
{
  "session_id": "abc-123",
  "video_id": "vid_abc12345",
  "status": "FAIL",
  "final_report": "Video contains 1 critical violation...",
  "compliance_results": [
    {
      "category": "Misleading Claims",
      "severity": "CRITICAL",
      "description": "Transcript states 'guaranteed results' at 0:32 — absolute guarantees are prohibited under CAP Code Rule 3.1."
    }
  ]
}
```

---

## Deployment

Every push to `main` runs a 3-stage GitHub Actions pipeline:

1. **Test** — `uv run pytest tests/` (build stops here if broken)
2. **Build & Push** — builds the Docker image, pushes to Docker Hub tagged
   `latest` and with the commit SHA (instant rollback to any prior build)
3. **Deploy** — SSHes into the production server with a dedicated deploy
   key, pulls the new image, recreates the API container, and syncs the
   latest static frontend files via `git pull`

The API runs in Docker behind [Caddy](https://caddyserver.com/) as a
reverse proxy on a self-managed Linux server, with automatic HTTPS via
Let's Encrypt. The frontend is served by Caddy as static files on the root
domain; the API is proxied on a dedicated `api.` subdomain.

---

## Observability

- **LangSmith** — full LangGraph trace debugging, node-level execution
  tracking
- **Azure Application Insights** *(optional)* — HTTP request logs, error
  tracking, performance metrics via OpenTelemetry; no-ops gracefully if
  unconfigured

---

## Security Notes

- All secrets managed via environment variables — never hardcoded
- `.env` excluded from the Docker build context via `.dockerignore`
- Azure auth uses a Service Principal scoped to the least-privilege
  **Video Indexer Account Contributor** role on the specific resource, not
  a broad Contributor role on the subscription
- CI/CD uses a dedicated, single-purpose SSH deploy key — separate from any
  personal credentials
- CORS is currently wide open (`allow_origins=["*"]`) — deliberate for this
  public demo tool with no user auth; would be tightened if auth or user
  data were ever added

---

## Tech Stack

`LangGraph` `LangChain` `OpenAI GPT-4o` `FastAPI` `Azure Video Indexer`
`Azure AI Search` `Docker` `Caddy` `GitHub Actions` `Docker Hub`
`LangSmith` `OpenTelemetry` `pytest` `uv` `Python 3.14`

---

## License

MIT License
