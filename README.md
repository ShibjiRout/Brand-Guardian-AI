# 🛡️ Brand Guardian AI
### Multi-modal YouTube Ad Compliance Auditing Engine

> AI-powered compliance auditing pipeline that ingests YouTube advertisements or uploaded video files, extracts speech-to-text transcripts and on-screen text (OCR), retrieves regulatory rules via RAG from indexed compliance PDFs, and uses GPT-4o to detect brand compliance violations — all orchestrated with LangGraph and deployed on Azure.

---

## 🌐 Live Demo

**[https://brandgurdian.azurewebsites.net](https://brandgurdian.azurewebsites.net)**

---

## 🏗️ Architecture

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
[FastAPI Backend + Async Job Polling] → [HTML Frontend]
```

### Core Components

| Layer | Technology |
|---|---|
| Orchestration | LangGraph StateGraph |
| Video Processing | Azure Video Indexer (OCR + Transcript) |
| Knowledge Base | Azure AI Search (Vector DB) |
| Embeddings | OpenAI text-embedding-3-small |
| LLM | OpenAI GPT-4o |
| API | FastAPI + Uvicorn (async job polling) |
| Observability | LangSmith + Azure Application Insights |
| Deployment | Docker → Azure Container Registry → Azure App Service |
| CI/CD | GitHub Actions (azure/login@v3, azure/webapps-deploy@v3) |

---

## 🔄 LangGraph Workflow

```
START → [index_video_node] → [audit_content_node] → END
```

**Node 1 — Video Indexer:**
- Option 1: Downloads YouTube video via yt-dlp, uploads to Azure Video Indexer
- Option 2: Accepts uploaded video file directly (bypasses yt-dlp for cloud environments)
- Polls until processing complete, extracts transcript and OCR text

**Node 2 — Compliance Auditor:**
- Embeds transcript + OCR using OpenAI text-embedding-3-small
- Retrieves top-3 relevant compliance rules from Azure AI Search (RAG)
- Sends to GPT-4o with retrieved rules and strict interpretation guidelines
- Returns structured JSON with violations, severity, and plain-English report

---

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- Azure subscription with:
  - Azure Video Indexer
  - Azure AI Search
  - Azure Blob Storage
  - Azure Application Insights
- OpenAI API key
- LangSmith account

### Installation

```bash
git clone https://github.com/ShibjiRout/Brand-Guardian-AI.git
cd Brand-Guardian-AI
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
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
AZURE_VI_ACCOUNT_ID="your-account-id"
AZURE_VI_LOCATION="germanywestcentral"
AZURE_VI_NAME="your-vi-name"
AZURE_SUBSCRIPTION_ID="your-subscription-id"
AZURE_RESOURCE_GROUP="your-resource-group"

# Azure Storage
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;..."

# Azure Monitor
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..."

# LangSmith
LANGCHAIN_TRACING_V2="true"
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY="lsv2_..."
LANGCHAIN_PROJECT="brand-guardian-prod"

# Azure Auth (for deployment)
AZURE_TENANT_ID="your-tenant-id"
AZURE_CLIENT_ID="your-client-id"
AZURE_CLIENT_SECRET="your-client-secret"
```

### Index Compliance Rules (PDF Upload)

Use the web UI **Step 1 panel** to upload compliance PDFs (e.g. CAP Code, FTC guidelines) directly into Azure AI Search. No manual scripts needed.

Or via API:

```bash
curl -X POST https://brandgurdian.azurewebsites.net/upload-rules \
  -F "files=@CAP-Code.pdf" \
  -F "clear_first=false"
```

To wipe the index and re-upload fresh rules:

```bash
curl -X POST https://brandgurdian.azurewebsites.net/clear-rules
```

### Run Locally

```bash
uv run uvicorn backend.src.api.server:app --reload
```

- App: `http://localhost:8000/app`
- API docs: `http://localhost:8000/docs`
- Architecture: `http://localhost:8000/architecture`

---

## 📁 Project Structure

```
brand-guardian-ai/
├── backend/
│   └── src/
│       ├── api/
│       │   ├── server.py        # FastAPI app — audit, status, rule upload endpoints
│       │   └── telemetry.py     # Azure Monitor / OpenTelemetry setup
│       ├── graph/
│       │   ├── state.py         # LangGraph state schema
│       │   ├── nodes.py         # Video Indexer + GPT-4o Auditor nodes
│       │   └── workflow.py      # LangGraph DAG definition
│       └── services/
│           ├── video_indexer.py # Azure Video Indexer service
│           └── rule_indexer.py  # PDF chunking + Azure AI Search indexer
├── frontend/
│   ├── index.html               # Landing page
│   ├── app.html                 # Audit tool UI
│   └── architecture.html        # High-level + low-level architecture diagrams
├── main.py                      # CLI entry point
├── Dockerfile
└── requirements.txt
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/audit` | Submit YouTube URL — returns `job_id` immediately |
| POST | `/audit-upload` | Upload video file + metadata — returns `job_id` immediately |
| GET | `/status/{job_id}` | Poll for audit job result |
| POST | `/upload-rules` | Upload PDF compliance rules into Azure AI Search |
| POST | `/clear-rules` | Delete all indexed compliance rules |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive Swagger UI |

### Async Job Flow

Audits run as background jobs to avoid gateway timeouts on cloud:

```bash
# 1. Submit audit
curl -X POST https://brandgurdian.azurewebsites.net/audit \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://youtu.be/your-video-id"}'
# → {"job_id": "abc-123"}

# 2. Poll for result
curl https://brandgurdian.azurewebsites.net/status/abc-123
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

## 📊 Observability

- **LangSmith** — Full LangGraph trace debugging, node-level execution tracking
- **Azure Application Insights** — HTTP request logs, error tracking, performance metrics via OpenTelemetry

---

## 🐳 Docker Deployment

```bash
docker build -t ytcompqa.azurecr.io/brand-guardian-api:latest .
docker push ytcompqa.azurecr.io/brand-guardian-api:latest
```

CI/CD is automated via GitHub Actions on every push to `main`.

---

## 🔒 Security

- All secrets managed via environment variables — never hardcoded
- `.env` excluded from Docker image via `.dockerignore`
- Azure Service Principal with scoped Contributor role

---

## 📋 Tech Stack

`LangGraph` `LangChain` `OpenAI GPT-4o` `FastAPI` `Azure Video Indexer` `Azure AI Search` `Azure Blob Storage` `Azure App Service` `Azure Container Registry` `Docker` `GitHub Actions` `LangSmith` `OpenTelemetry` `Azure Application Insights` `Python 3.12`

---

## 📄 License

MIT License
