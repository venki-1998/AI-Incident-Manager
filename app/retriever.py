# app/retriever.py (MODIFIED)
from langchain_community.vectorstores import Qdrant
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

# Initialize embeddings
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

def get_retriever(as_retriever=True): # <--- Added argument
    """
    Returns a Qdrant vectorstore object or a retriever for the 'incidents' collection.
    """
    # Connect to your running Qdrant instance
    qdrant_client = QdrantClient(url="http://qdrant:6333")

    # Initialize the Qdrant vectorstore
    vectorstore = Qdrant(
        client=qdrant_client,
        collection_name="incidents",
        embeddings=embeddings
    )

    if as_retriever:
        # Return a retriever object (causes error in your environment)
        return vectorstore.as_retriever()
    else:
        # Return the vectorstore object itself (recommended workaround)
        return vectorstore