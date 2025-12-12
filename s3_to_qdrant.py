#!/usr/bin/env python3
"""
s3_to_qdrant.py

Standalone ingestion script:
- Lists objects under an S3 bucket/prefix
- Downloads documents locally
- Loads & splits documents into chunks
- Computes embeddings via HuggingFaceEmbeddings
- Upserts chunks into Qdrant with deterministic chunk IDs (md5 of key+index)

Usage example:
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_REGION=...
    export QDRANT_URL="http://localhost:6333"
    python s3_to_qdrant.py \
        --bucket my-bucket \
        --prefix rcas/ \
        --collection incidents \
        --delete-local \
        --dry-run False
"""

import os
import sys
import argparse
import hashlib
import tempfile
import pathlib
import json
from typing import List, Dict, Tuple

import boto3
from botocore.exceptions import ClientError

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

from langchain_huggingface import HuggingFaceEmbeddings
# Use the Qdrant class from langchain-qdrant to match your stack
from langchain_qdrant import Qdrant

# LangChain document loaders & splitters (v1+)
from langchain_community.document_loaders import (
    S3DirectoryLoader,
    TextLoader,
    PyPDFLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ---------- Utilities ----------
def md5_id(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def ensure_local_dir(path: str):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


# ---------- S3 Helpers ----------
def list_s3_objects(bucket: str, prefix: str) -> List[Dict]:
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    objs = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            # skip "folders" (keys that end with '/')
            if item["Key"].endswith("/"):
                continue
            objs.append(item)
    return objs


def download_s3_object(bucket: str, key: str, dest_dir: str) -> Tuple[str, Dict]:
    s3 = boto3.client("s3")
    ensure_local_dir(dest_dir)
    local_path = os.path.join(dest_dir, os.path.basename(key))
    try:
        s3.download_file(bucket, key, local_path)
        head = s3.head_object(Bucket=bucket, Key=key)
        metadata = {
            "Key": key,
            "LastModified": head.get("LastModified").isoformat() if head.get("LastModified") else None,
            "Size": head.get("ContentLength"),
            "ETag": head.get("ETag"),
        }
        return local_path, metadata
    except ClientError as e:
        print(f"ERROR downloading s3://{bucket}/{key} -> {e}")
        raise


# ---------- Document processing ----------
def choose_loader_for_path(path: str):
    suffix = pathlib.Path(path).suffix.lower()
    if suffix == ".pdf":
        return UnstructuredPDFLoader(path)
    if suffix in [".docx", ".doc"]:
        return UnstructuredWordDocumentLoader(path)
    # fallback to TextLoader for .txt, .md, .log, etc.
    return TextLoader(path, encoding="utf-8")


def load_and_split(path: str, chunk_size: int = 800, chunk_overlap: int = 100):
    loader = choose_loader_for_path(path)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(docs)


# ---------- Qdrant helpers ----------
def ensure_qdrant_collection(client: QdrantClient, collection_name: str, vector_size: int = 384):
    existing = [c.name for c in client.get_collections().collections]
    if collection_name in existing:
        print(f"Qdrant: collection '{collection_name}' already exists")
        return
    print(f"Qdrant: creating collection '{collection_name}' (size={vector_size})")
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upsert_chunks_to_qdrant(
    vectorstore: Qdrant,
    docs_chunks,
    s3_key: str,
    metadata_base: Dict,
    dry_run: bool = False,
):
    texts = []
    metadatas = []
    ids = []

    for i, chunk in enumerate(docs_chunks):
        text = chunk.page_content
        # deterministic id so re-ingestion updates the same chunk
        chunk_id = md5_id(f"{s3_key}::{i}")
        meta = dict(metadata_base)  # copy
        meta.update(
            {
                "s3_key": s3_key,
                "filename": metadata_base.get("filename"),
                "chunk_index": i,
            }
        )
        texts.append(text)
        metadatas.append(meta)
        ids.append(chunk_id)

    print(f"Prepared {len(texts)} chunks for s3_key='{s3_key}'.")
    if dry_run:
        print("DRY RUN: not writing to Qdrant. Example IDs:", ids[:3])
        return len(texts)

    # add_texts supports ids and metadatas
    vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return len(texts)


# ---------- Main ingestion ----------
def ingest_from_s3(
    bucket: str,
    prefix: str,
    collection_name: str = "incidents",
    local_tmp_dir: str = None,
    delete_local: bool = True,
    dry_run: bool = True,
):
    if local_tmp_dir is None:
        local_tmp_dir = tempfile.mkdtemp(prefix="s3_ingest_")
    else:
        ensure_local_dir(local_tmp_dir)

    print(f"Using temporary dir: {local_tmp_dir} (delete_local={delete_local})")
    s3_objs = list_s3_objects(bucket, prefix)
    if not s3_objs:
        print(f"No objects found in s3://{bucket}/{prefix}")
        return 0

    # Initialize Qdrant client & embeddings & vectorstore
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_client = QdrantClient(url=qdrant_url)
    ensure_qdrant_collection(qdrant_client, collection_name, vector_size=384)

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectorstore = Qdrant(client=qdrant_client, collection_name=collection_name, embeddings=embeddings)

    total_chunks = 0
    for obj in s3_objs:
        key = obj["Key"]
        print(f"\nProcessing s3://{bucket}/{key} ...")
        try:
            local_path, head_meta = download_s3_object(bucket, key, local_tmp_dir)
        except Exception as e:
            print(f"Skipping {key} due to download error: {e}")
            continue

        try:
            docs_chunks = load_and_split(local_path)
            metadata_base = {
                "filename": pathlib.Path(local_path).name,
                "s3_last_modified": head_meta.get("LastModified"),
                "s3_size": head_meta.get("Size"),
            }
            count = upsert_chunks_to_qdrant(vectorstore, docs_chunks, key, metadata_base, dry_run=dry_run)
            total_chunks += count
            print(f"Upserted {count} chunks for {key}")
        except Exception as e:
            print(f"Error processing {local_path}: {e}")
        finally:
            if delete_local:
                try:
                    os.remove(local_path)
                except OSError:
                    pass

    print(f"\nIngestion complete. Total chunks processed: {total_chunks}")
    return total_chunks


# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Ingest documents from S3 into Qdrant")
    p.add_argument("--bucket", required=True, help="S3 bucket name")
    p.add_argument("--prefix", default="", help="S3 prefix/folder to read")
    p.add_argument("--collection", default="incidents", help="Qdrant collection name")
    p.add_argument("--local-dir", default=None, help="Local temporary directory (optional)")
    p.add_argument("--no-delete-local", action="store_true", help="Do not delete downloaded local files")
    p.add_argument("--dry-run", action="store_true", help="Prepare but do not write to Qdrant")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    ingest_from_s3(
        bucket=args.bucket,
        prefix=args.prefix,
        collection_name=args.collection,
        local_tmp_dir=args.local_dir,
        delete_local=not args.no_delete_local,
        dry_run=args.dry_run,
    )
