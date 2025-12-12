# app/main.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Correct initialization for RunnableSequence (using multiple args, not a list)
from langchain_core.runnables import RunnableSequence, RunnableLambda 
from langchain_groq import ChatGroq

from app.prompts import incident_prompt
from app.retriever import get_retriever
from app.metrics import start_metrics_server, INCIDENTS_PROCESSED

load_dotenv()

app = FastAPI(title="AI Incident Monitoring RAG Service")

# ---------------------------
# Initialize retriever
vector_store = get_retriever(as_retriever=False) # <--- REQUIRES CHANGE IN retriever.py

# ---------------------------
# Runnable for retrieving docs & creating string context
def retrieve_docs(inputs):
    query = inputs["input"]
    # USE THE DIRECT SIMILARITY SEARCH METHOD FROM THE VECTORSTORE
    # This is a common method that is always available on the Qdrant/VectorStore object
    docs = vector_store.similarity_search(query) 
    context = "\n".join([doc.page_content for doc in docs])
    return {"input": query, "context": context}

retriever_runnable = RunnableLambda(retrieve_docs)
# ---------------------------
# Runnable for calling Groq LLM
def llm_call(inputs):
    llm = ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    )
    final_input = incident_prompt.format(input=inputs["input"], context=inputs["context"])
    return {"analysis": llm.invoke(final_input).content}

llm_runnable = RunnableLambda(llm_call)

# ---------------------------
# Combine Runnables into a RAG chain
# FIX: Passed runnables as individual arguments, not a list
rag_chain = RunnableSequence(retriever_runnable, llm_runnable) 

# ---------------------------
# Pydantic schema
class Incident(BaseModel):
    message: str

# ---------------------------
# Startup event
@app.on_event("startup")
def on_startup():
    start_metrics_server()
    print("🚀 RAG service & Prometheus metrics started")

# ---------------------------
# POST endpoint for incidents
@app.post("/incident")
async def handle_incident(incident: Incident):
    INCIDENTS_PROCESSED.inc()
    try:
        result = rag_chain.invoke({"input": incident.message})
        return result
    except Exception as e:
        # NOTE: You should consider logging the full exception 'e' here for debugging
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------------------------
# Alert 
# ---------------------------
# Alert Pydantic models for Alertmanager
from pydantic import BaseModel
from typing import List, Dict, Optional
import httpx

class AlertLabel(BaseModel):
    alertname: str
    severity: Optional[str] = None
    instance: Optional[str] = None

class AlertAnnotation(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None

class Alert(BaseModel):
    labels: AlertLabel
    annotations: AlertAnnotation

class AlertManagerPayload(BaseModel):
    alerts: List[Alert]

# ---------------------------
# Updated /alert endpoint using Pydantic
# ---------------------------
# ---------------------------
# At the top, import boto3
import boto3

# Initialize SNS client
sns_client = boto3.client(
    "sns",
    region_name=os.getenv("AWS_REGION", "us-east-1")  # default region if not in .env
)
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")  # set this in your .env file

# ---------------------------
# Updated /alert endpoint with SNS
@app.post("/alert")
async def receive_alert(payload: AlertManagerPayload):
    """
    Receives Prometheus alerts from Alertmanager
    and calls the /incident endpoint automatically.
    Also sends an email via SNS with the RCA.
    """
    responses = []

    for alert in payload.alerts:
        # Access Pydantic attributes, not dict keys
        name = alert.labels.alertname
        description = alert.annotations.description or alert.annotations.summary
        if not description:
            description = f"Alert {name} fired without description"

        print(f"🚨 Alert received: {name} — {description}")

        # Call existing /incident logic on correct port
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8081/incident",
                json={"message": description}
            )
            ai_response = resp.json()

        responses.append({
            "alert": name,
            "description": description,
            "ai_recommendation": ai_response
        })

        # ---------------------------
        # Send email via SNS
        if SNS_TOPIC_ARN:
            try:
                subject = f"[AI-RAG Alert] {name}"
                message = f"Alert: {name}\nDescription: {description}\n\nAI RCA/Analysis:\n{ai_response['analysis']}"
                sns_client.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Message=message,
                    Subject=subject
                )
                print(f"✅ Published alert '{name}' to SNS")
            except Exception as e:
                print(f"❌ Failed to send SNS alert for '{name}': {e}")

    return {"processed_alerts": responses}

# ---------------------------
# Run server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)