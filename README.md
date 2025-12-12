# AI Incident Monitoring RAG Service

This project implements a **RAG (Retrieval-Augmented Generation) Service** for AI-driven incident analysis. It automatically processes alerts from **Prometheus/Alertmanager**, retrieves relevant historical data from **Qdrant**, and generates detailed root cause analysis (RCA) using **Groq LLM**.  

---

## 🚀 Components

The system consists of the following services running via **Docker Compose**:

| Service        | Purpose                                                                 | Port  |
|----------------|-------------------------------------------------------------------------|-------|
| **RAG Service**| FastAPI app that processes alerts, retrieves context, calls Groq LLM    | 8081  |
| **Prometheus** | Metrics and alert monitoring                                            | 9090  |
| **Alertmanager** | Receives Prometheus alerts and forwards them to RAG service           | 9093  |
| **Grafana**    | Dashboard for metrics visualization                                     | 3000  |
| **Qdrant**     | Vector database for storing document embeddings                        | 6333  |
| **Postgres**   | Stores incident-related data                                            | 5432  |
| **Redpanda**   | Kafka-compatible event streaming                                        | 9092  |

---

## 📦 Prerequisites

- Docker & Docker Compose
- Python 3.10+
- `.env` file with the following keys:
  ```bash
    # Hugging Face (optional if using HF inference)
    HF_API_TOKEN=YOUR_HF_TOKEN_HERE
    EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
    # Redpanda
    KAFKA_BOOTSTRAP=redpanda:9092
    KAFKA_TOPIC=incidents

    # Qdrant
    QDRANT_HOST=qdrant
    QDRANT_PORT=6333
    QDRANT_COLLECTION=incidents

    # Postgres
    POSTGRES_URL=postgresql://aiuser:aisecret@postgres:5432/incidents

    # Hugging Face
    HF_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
    HF_API_TOKEN=          # optional if you use HF Inference API (not required for local sentence-transformers)

    # Groq
    GROQ_API_KEY="LsP8otqH3hjIb"
    GROQ_API_URL=https://api.groq.ai/v1   # keep default unless you have another endpoint
    GROQ_MODEL="llama-3.3-70b-versatile"

    # Optional tuning
    RAG_TOP_K=5

    # Aws variables
    export AWS_ACCESS_KEY_ID=""
    export AWS_SECRET_ACCESS_KEY=""
    export AWS_REGION=us-east-1
    export SNS_TOPIC_ARN="arn:aws:sns:us-east-1:XXXXXX:ai-incident-alerts"

⚙️ Setup

Clone the repository

git clone https://github.com/shan5a6/langchain-ai-incident-manager.git
cd langchain-ai-incident-monitor


Start all services using Docker Compose

docker-compose up -d


Verify services

RAG Service: http://localhost:8081/health
Prometheus: http://localhost:9090
Alertmanager: http://localhost:9093
Grafana: http://localhost:3000

📝 Usage
1. Trigger an Incident

Use the /incident endpoint to test manually:

curl -X POST http://localhost:8081/incident \
-H "Content-Type: application/json" \
-d '{"message": "Production DB instance is down"}'

Response will include AI-generated RCA based on historical incidents stored in Qdrant.

2. Prometheus Alert Integration

Add alert rules in Prometheus:
groups:
- name: database_alerts
  rules:
  - alert: PostgresDown
    expr: pg_up == 0
    for: 10s
    labels:
      severity: critical
    annotations:
      summary: "Postgres service is not responding for the last 10 seconds"
      description: "Production Postgres service is down."


Configure Alertmanager to send alerts to RAG Service:

receivers:
  - name: 'rag-service'
    webhook_configs:
      - url: 'http://rag-service:8081/alert'


Once the alert triggers, Alertmanager calls /alert, which invokes /incident and generates AI-driven RCA.

3. Metrics & Observability

Prometheus collects metrics from RAG Service (custom INCIDENTS_PROCESSED counter).

Grafana can be connected to Prometheus to visualize metrics and alert history.

📂 Folder Structure
ai-incident-monitor/
├─ app/
│  ├─ main.py            # FastAPI RAG service
│  ├─ retriever.py       # Qdrant retriever logic
│  ├─ prompts.py         # Predefined prompts for Groq LLM
│  ├─ metrics.py         # Prometheus metrics integration
│  ├─ ingestion.py       # S3 to Qdrant ingestion script
│  └─ create-collection-qdrant.py # Qdrant setup
├─ docker-compose.yml
├─ prometheus.yml
├─ alertmanager.yml
├─ .env
├─ README.md
s3_documents/
├── api
│   └── api_500_error_rca.txt
├── backend
│   └── memory_leak_rca.txt
├── cicd
│   └── sonar-qube-issues.txt
├── database
│   ├── db_outage_rca.txt
│   └── db_performance_issue.txt
└── frontend
    └── latency_issue_rca.txt
└─ .gitignore

🛠️ Commands
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f rag-service

# Test incident API
curl -X POST http://localhost:8081/incident \
-H "Content-Type: application/json" \
-d '{"message": "Production DB instance is down"}'

# Trigger alert manually (for testing)
curl -X POST http://localhost:8081/alert \
-H "Content-Type: application/json" \
-d '{"alerts":[{"labels":{"alertname":"TestAlert"},"annotations":{"summary":"Test alert fired"}}]}'

🔑 Features

RAG-powered Incident Analysis using historical context from Qdrant.

Alert Integration with Prometheus/Alertmanager.
Metrics with Prometheus (INCIDENTS_PROCESSED).
AI Recommendations using Groq LLM.
Dockerized for easy deployment.
📧 Optional: Email Notification

You can integrate AWS SNS to automatically send RCA results via email. On receiving a /alert, call SNS publish() with ai_recommendation as the message.