from langchain_qdrant import Qdrant  # Use updated package
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import uuid

# Initialize embeddings
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Connect to Qdrant
qdrant_client = QdrantClient(url="http://localhost:6333")
collection_name = "incidents"

# Create collection if it doesn't exist
existing_collections = [col.name for col in qdrant_client.get_collections().collections]
if collection_name not in existing_collections:
    qdrant_client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    print(f"✅ Created collection '{collection_name}'")

# Initialize vectorstore
vectorstore = Qdrant(
    client=qdrant_client,
    collection_name=collection_name,
    embeddings=embeddings
)

# Sample documents to add
sample_docs = [
    "Production DB instance is down",
    "Frontend server is experiencing latency issues",
    "API gateway is returning 500 errors",
    "Memory usage on backend server exceeded threshold",
    "Disk space running low on database server"
]

# Generate UUIDs for IDs
ids = [str(uuid.uuid4()) for _ in sample_docs]

# Add documents to the collection
vectorstore.add_texts(
    texts=sample_docs,
    ids=ids
)

print(f"✅ Added {len(sample_docs)} documents to '{collection_name}' collection")