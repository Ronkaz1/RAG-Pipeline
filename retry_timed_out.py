import os
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
OLLAMA_EMBED_MODEL = "nomic-embed-text"
RETRY_TIMEOUT_SECONDS = 600
TRACKER_FILE = "doc_tracker.json"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
# =========================================================

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tracker(tracker):
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2)

def get_file_hash(file_path: Path) -> str:
    return hashlib.md5(file_path.read_bytes()).hexdigest()

def main():
    print(f"[{datetime.now()}] Starting retry for timed-out files...\n")
    tracker = load_tracker()

    timed_out = {k: v for k, v in tracker.items() if v.get('status') == 'timed_out'}
    if not timed_out:
        print("No timed-out files found. Nothing to retry.")
        return

    print(f"Found {len(timed_out)} timed-out file(s) to retry.\n")

    # LlamaIndex setup (once)
    from llama_index.core import Settings, Document
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from llama_index.core.readers import SimpleDirectoryReader
    from qdrant_client import QdrantClient

    Settings.embed_model = OllamaEmbedding(model_name=OLLAMA_EMBED_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME, batch_size=64)
    pipeline = IngestionPipeline(transformations=[Settings.node_parser], vector_store=vector_store)

    recovered = 0
    still_failing = 0

    for key, info in list(timed_out.items()):
        file_path = Path(key)
        if not file_path.exists():
            print(f" ⚠ Skipping — file no longer exists: {file_path.name}")
            continue

        size_kb = file_path.stat().st_size / 1024
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Retrying: {file_path.name} ({size_kb:,.1f} KB)")

        try:
            # Try loading with LlamaIndex first (what's working)
            reader = SimpleDirectoryReader(input_files=[str(file_path)], filename_as_id=True)
            documents: List[Document] = reader.load_data()

            print(f"   Loaded {len(documents)} document(s)")

            # Add metadata
            for doc in documents:
                doc.metadata.update({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "last_modified": str(file_path.stat().st_mtime),
                    "retry_attempt": True
                })

            # Ingest
            nodes = pipeline.run(documents=documents, show_progress=True)

            current_hash = get_file_hash(file_path)
            tracker[key] = {
                "hash": current_hash,
                "mtime": file_path.stat().st_mtime,
                "last_indexed": time.time(),
                "status": "ok",
                "nodes": len(nodes),
                "retry_success": True
            }
            recovered += 1
            print(f"   ✓ Recovered — {len(nodes)} nodes indexed")

        except Exception as e:
            err_str = str(e)
            print(f"   ❌ Failed: {type(e).__name__}: {err_str[:200]}...")

            # Optional: Try pypdf fallback for stubborn PDFs
            if file_path.suffix.lower() == '.pdf' and "pdf" in err_str.lower():
                print("   🔄 Trying pypdf fallback for PDF...")
                try:
                    from pypdf import PdfReader
                    reader_pdf = PdfReader(str(file_path))
                    documents = []
                    for i, page in enumerate(reader_pdf.pages):
                        text = page.extract_text() or ""
                        if text.strip():
                            documents.append(Document(
                                text=text,
                                metadata={
                                    "file_path": str(file_path),
                                    "file_name": file_path.name,
                                    "page_num": i + 1,
                                    "last_modified": str(file_path.stat().st_mtime),
                                    "retry_pdf_fallback": True
                                }
                            ))
                    if documents:
                        nodes = pipeline.run(documents=documents, show_progress=True)
                        current_hash = get_file_hash(file_path)
                        tracker[key] = {
                            "hash": current_hash,
                            "mtime": file_path.stat().st_mtime,
                            "last_indexed": time.time(),
                            "status": "ok",
                            "nodes": len(nodes),
                            "retry_pdf_fallback": True
                        }
                        recovered += 1
                        print(f"   ✓ PDF fallback succeeded — {len(nodes)} nodes")
                        save_tracker(tracker)
                        continue
                except Exception as pdf_e:
                    print(f"   ❌ PDF fallback also failed: {pdf_e}")

            # Mark as failed
            tracker[key]['status'] = 'error'
            tracker[key]['error'] = err_str
            tracker[key]['last_retry'] = time.time()
            still_failing += 1

        save_tracker(tracker)   # save after every file

    print(f"\n{'='*60}")
    print(f"Retry complete!")
    print(f"   Recovered: {recovered}")
    print(f"   Still failing: {still_failing}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()