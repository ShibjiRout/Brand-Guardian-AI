# 🛡️ Brand Guardian AI
### Multi-modal YouTube Ad Compliance Auditing Engine

> AI-powered compliance auditing pipeline that ingests YouTube advertisements, extracts speech-to-text transcripts and on-screen text (OCR), retrieves regulatory rules via RAG, and uses GPT-4o to detect brand compliance violations — all orchestrated with LangGraph and deployed on Azure.

---

## 🏗️ Architecture

```
[YouTube URL]
      ↓
[yt-dlp Download] → [Azure Blob Storage (temp)]
      ↓
[Azure Video Indexer] → [Transcript + OCR Extraction]
      ↓
[Azure AI Search Vector DB] ← [OpenAI Embeddings RAG Retrieval]
      ↓
[GPT-4o Compliance Auditor] → [Structured Violation Report]
      ↓
[FastAPI Backend] → [HTML Frontend]
```

### Core Components

| Layer | Technology |
|---|---|
| Orchestration | LangGraph StateGraph |
| Video Processing | Azure Video Indexer (OCR + Transcript) |
| Knowledge Base | Azure AI Search (Vector DB) |
| Embeddings | OpenAI text-embedding-3-small |
| LLM | OpenAI GPT-4o |
| API | FastAPI + Uvicorn |
| Observability | LangSmith + Azure Application Insights |
| Deployment | Docker → Azure Container Registry → Azure App Service |

---

## 🔄 LangGraph Workflow

```
START → [index_video_node] → [audit_content_node] → END
```

**Node 1 — Video Indexer:**
- Downloads YouTube video via yt-dlp
- Uploads to Azure Video Indexer
- Polls until processing complete
- Extracts transcript and OCR text

**Node 2 — Compliance Auditor:**
- Embeds transcript + OCR using OpenAI
- Retrieves top-3 relevant compliance rules from Azure AI Search (RAG)
- Sends to GPT-4o with retrieved rules as context
- Returns structured JSON with violations and severity

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
git clone https://github.com/your-username/brand-guardian-ai.git
cd brand-guardian-ai
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

### Index Compliance Documents

Add your compliance PDF files to `backend/data/` then run:

```bash
cd backend/scripts
python index_documents.py
```

This chunks and indexes your PDFs into Azure AI Search.

### Run Locally (CLI)

```bash
python main.py
```

### Run Locally (API)

```bash
uv run uvicorn backend.src.api.server:app --reload
```

API docs available at: `http://localhost:8000/docs`

---

## 📁 Project Structure

```
brand-guardian-ai/
├── backend/
│   ├── data/                    # Compliance PDF documents
│   ├── scripts/
│   │   └── index_documents.py   # PDF → Azure AI Search indexer
│   └── src/
│       ├── api/
│       │   ├── server.py        # FastAPI application
│       │   └── telemetry.py     # Azure Monitor setup
│       ├── graph/
│       │   ├── state.py         # LangGraph state schema
│       │   ├── nodes.py         # Indexer + Auditor nodes
│       │   └── workflow.py      # LangGraph DAG definition
│       └── services/
│           └── video_indexer.py # Azure Video Indexer service
├── main.py                      # CLI entry point
├── Dockerfile                   # Docker configuration
├── .dockerignore
├── requirements.txt
└── brand_guardian.html          # Frontend UI
```

---

## 🐳 Docker Deployment

### Build and Push to Azure Container Registry

```bash
docker build -t ytcompqa.azurecr.io/brand-guardian-api:latest .
docker login ytcompqa.azurecr.io -u your-username -p your-password
docker push ytcompqa.azurecr.io/brand-guardian-api:latest
```

### Deploy to Azure App Service

1. Create Azure Web App with container from ACR
2. Set all environment variables in **Settings → Environment Variables**
3. Enable **Managed Identity** for Azure resource access
4. Set startup command:
```
uvicorn backend.src.api.server:app --host 0.0.0.0 --port 8000
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/audit` | Submit YouTube URL for compliance audit |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive Swagger UI |

### Example Request

```bash
curl -X POST https://brandgurdian.azurewebsites.net/audit \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://youtu.be/your-video-id"}'
```

### Example Response

```json
{
  "session_id": "ce6c43bb-c71a-4f16-a377-8b493502fee2",
  "video_id": "vid_ce6c43bb",
  "status": "FAIL",
  "final_report": "Video contains 2 critical violations...",
  "compliance_results": [
    {
      "category": "Claim Validation",
      "severity": "CRITICAL",
      "description": "Absolute guarantee detected — requires substantiation."
    }
  ]
}
```

---

## 📊 Observability

- **LangSmith** — Full LangGraph trace debugging, node-level execution tracking, and workflow observability
- **Azure Application Insights** — HTTP request logs, error tracking, performance metrics via OpenTelemetry

---

## 🔒 Security

- Azure Service Principal with Contributor role for Video Indexer access
- All secrets managed via environment variables — never hardcoded
- `.env` excluded from Docker image via `.dockerignore`
- Azure Key Vault integration recommended for production

---

## 📋 Tech Stack

`LangGraph` `LangChain` `OpenAI GPT-4o` `FastAPI` `Azure Video Indexer` `Azure AI Search` `Azure Blob Storage` `Azure App Service` `Azure Container Registry` `Docker` `LangSmith` `OpenTelemetry` `Azure Application Insights` `yt-dlp` `Python 3.12`

---

## 📄 License

MIT License