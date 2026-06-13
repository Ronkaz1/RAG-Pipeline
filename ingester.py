import os
import sys
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import List

# ========================= CONFIG =========================
SOURCE_FOLDER = r"\\bigbertha\Data\Companies_Clients\NRF\BG India NRF"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "bertha_docs"
OLLAMA_EMBED_MODEL = "nomic-embed-text"  # fast & good
TRACKER_FILE = "doc_tracker.json"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
NUM_WORKERS = 4  # adjust based on your CPU + Ollama NUM_PARALLEL
BATCH_SIZE = 64  # for Qdrant upserts
# =========================================================

def get_file_hash(file_path: Path) -> str:
    return hashlib.md5(file_path.read_bytes()).hexdigest()

def load_tracker() -> dict:
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tracker(tracker: dict):
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2)

def main():
    print(f"[{datetime.now()}] Starting incremental ingestion...")
    source_path = Path(SOURCE_FOLDER)
    if not source_path.exists():
        print(f"Error: Folder not found!")
        sys.exit(1)

    tracker = load_tracker()

    # Setup Qdrant
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE)
        )
    print(f"Collection ready. Current vectors: {client.count(COLLECTION_NAME).count}")

    # LlamaIndex setup (global once)
    from llama_index.core import Settings, Document
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from llama_index.core.storage.docstore import SimpleDocumentStore
    from llama_index.core.storage.index_store import SimpleIndexStore
    from llama_index.core import StorageContext

    Settings.embed_model = OllamaEmbedding(model_name=OLLAMA_EMBED_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        batch_size=BATCH_SIZE,      # important for bulk
        parallel=2                  # parallel uploads
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Optional: persist docstore for better dedup/resume
    storage_context.docstore = SimpleDocumentStore()
    storage_context.index_store = SimpleIndexStore()

    pipeline = IngestionPipeline(
        transformations=[Settings.node_parser],
        vector_store=vector_store,  # or handle manually
    )

    supported_ext = {'.pdf', '.txt', '.md', '.docx', '.doc', '.pptx', '.ppt',
                     '.xlsx', '.xls', '.csv', '.html', '.htm', '.json', '.xml'}

    files_to_process: List[Path] = []
    for file_path in sorted(source_path.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in supported_ext:
            continue
        key = str(file_path)
        current_hash = get_file_hash(file_path)
        tracked = tracker.get(key)
        if tracked and tracked.get("hash") == current_hash:
            continue
        files_to_process.append((file_path, current_hash))

    print(f"Found {len(files_to_process)} new/updated files to process.")

    processed = 0
    for file_path, current_hash in files_to_process:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] → Processing: {file_path.name} ({file_path.stat().st_size / 1024:,.1f} KB)")

        try:
            from llama_index.core.readers import SimpleDirectoryReader
            documents: List[Document] = SimpleDirectoryReader(input_files=[str(file_path)]).load_data()

            # Add metadata
            for doc in documents:
                doc.metadata.update({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "last_modified": str(file_path.stat().st_mtime),
                    "source": "NRF_BG_India"
                })

            # Run pipeline with parallelism
            nodes = pipeline.run(documents=documents, num_workers=NUM_WORKERS, show_progress=True)

            tracker[str(file_path)] = {
                "hash": current_hash,
                "mtime": file_path.stat().st_mtime,
                "last_indexed": time.time(),
                "status": "ok",
                "nodes": len(nodes)
            }
            processed += 1
            print(f" ✓ {file_path.name} — {len(nodes)} nodes indexed")

        except Exception as e:
            print(f" ❌ Error processing {file_path.name}: {e}")
            tracker[str(file_path)] = {
                "hash": current_hash,
                "mtime": file_path.stat().st_mtime,
                "last_indexed": time.time(),
                "status": "error",
                "error": str(e)
            }
        save_tracker(tracker)  # save after each for resume safety

    save_tracker(tracker)
    print(f"\n✅ Ingestion complete! Processed {processed} new/updated documents.")

if __name__ == "__main__":
    main()