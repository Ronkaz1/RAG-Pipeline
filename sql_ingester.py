import os
import sys
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path

import pymssql
from llama_index.core import VectorStoreIndex, Settings, StorageContext, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# ========================= CONFIG =========================
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
EMBED_DIM = 768
COLLECTION_NAME = "bertha_docs"
OLLAMA_EMBED_MODEL = "nomic-embed-text"   # or "mxbai-embed-large"

TRACKER_FILE = "sql_tracker.json"

# SQL Configuration
DB_SERVER   = "YOUR_SQL_SERVER"
DB_PORT = 1433
DB_NAME = "ged"
DB_USER     = "YOUR_DB_USER"
DB_PASSWORD = "YOUR_DB_PASSWORD"

SQL_QUERY = """
SELECT DISTINCT 
    a.r_seq, 
    b.r_title, 
    CAST(a.data AS NVARCHAR(MAX)) AS data
FROM f_text_rec a
JOIN f_record b ON a.r_seq = b.r_seq
where a.r_seq < 364610
ORDER BY a.r_seq DESC;
"""

# =========================================================

def get_row_hash(r_seq: int, title: str, data: str) -> str:
    content = f"{r_seq}|{title}|{data}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tracker(tracker):
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2)

def setup_index():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE)
        )

    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    Settings.embed_model = OllamaEmbedding(model_name=OLLAMA_EMBED_MODEL, embed_batch_size=50)
    Settings.node_parser = SentenceSplitter(chunk_size=800, chunk_overlap=100)

    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

    print(f"Index ready. Current vectors: {client.count(COLLECTION_NAME).count}")
    return index

def main():
    print(f"[{datetime.now()}] Starting incremental SQL ingestion...")
    
    tracker = load_tracker()
    index = setup_index()
    
    processed = 0
    conn = None
    
    try:
        conn = pymssql.connect(server=DB_SERVER, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, conn_properties='')
        cursor = conn.cursor()
        
        print("Executing query...")
        cursor.execute(SQL_QUERY)
        
        BATCH_SIZE = 50
        batch_docs = []
        batch_tracker_entries = {}
        parser = SentenceSplitter(chunk_size=800, chunk_overlap=100)

        def flush_batch():
            nonlocal processed
            if not batch_docs:
                return
            print(f"\nEmbedding and inserting batch of {len(batch_docs)} documents...")
            nodes = parser.get_nodes_from_documents(batch_docs, show_progress=True)
            index.insert_nodes(nodes, show_progress=True)
            processed += len(batch_docs)
            tracker.update(batch_tracker_entries)
            save_tracker(tracker)
            batch_docs.clear()
            batch_tracker_entries.clear()

        for row in cursor.fetchall():
            r_seq, r_title, data = row[0], row[1], row[2]

            if not data or str(data).strip() == "":
                continue

            key = f"sql_row_{r_seq}"
            current_hash = get_row_hash(r_seq, r_title, data)

            tracked = tracker.get(key)
            if tracked and tracked.get("hash") == current_hash:
                continue

            print(f"â†’ Queued: ID {r_seq} - {r_title[:60]}...")

            batch_docs.append(Document(
                text=f"ID: {r_seq} {r_title}: {data}",
                metadata={
                    "source": "sql_database",
                    "table": "f_text_rec + f_record",
                    "r_seq": int(r_seq),
                    "r_title": r_title,
                    "last_indexed": datetime.now().isoformat()
                }
            ))
            batch_tracker_entries[key] = {
                "hash": current_hash,
                "r_seq": int(r_seq),
                "r_title": r_title,
                "last_indexed": time.time()
            }

            if len(batch_docs) >= BATCH_SIZE:
                flush_batch()

        flush_batch()  # insert any remaining docs
                
    except Exception as e:
        print(f"âŒ Error: {e}")
    finally:
        if conn:
            conn.close()
    
    save_tracker(tracker)
    print(f"\nâœ… SQL Ingestion complete! Processed {processed} new/updated records.")

if __name__ == "__main__":
    main()
