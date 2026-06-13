import os
import json
import time
from pathlib import Path
from datetime import datetime

# ========================= CONFIG =========================
RAG_ROOT         = r"D:\RAG"
TRACKER_FILE     = r"D:\RAG\_ingest_tracker.json"
QDRANT_HOST      = "localhost"
QDRANT_PORT      = 6333
COLLECTION_NAME  = "rag_summaries"
EMBED_MODEL      = "nomic-embed-text"
CHUNK_SIZE       = 1024    # summaries are dense; larger chunks work well
CHUNK_OVERLAP    = 64
BATCH_SIZE       = 64
NUM_WORKERS      = 4
# =========================================================


def ts():
    return datetime.now().strftime("%H:%M:%S")


def load_tracker() -> dict:
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_tracker(tracker: dict):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2)


def build_document_text(summary_obj: dict) -> str:
    """Combine summary fields into a single rich text for embedding."""
    parts = []

    doc_type = summary_obj.get("document_type", "")
    if doc_type:
        parts.append(f"Document type: {doc_type}")

    file_name = summary_obj.get("file_name", "")
    if file_name:
        parts.append(f"File: {file_name}")

    topics = summary_obj.get("key_topics", [])
    if topics:
        parts.append(f"Key topics: {', '.join(topics)}")

    entities = summary_obj.get("entities", [])
    if entities:
        parts.append(f"Entities: {', '.join(entities)}")

    summary = summary_obj.get("summary", "")
    if summary:
        parts.append(summary)

    return "\n\n".join(parts)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting RAG ingester")
    print(f"  Source   : {RAG_ROOT}  (summary JSONs)")
    print(f"  Qdrant   : {QDRANT_HOST}:{QDRANT_PORT}  collection={COLLECTION_NAME}")
    print(f"  Workers  : {NUM_WORKERS}\n")

    # LlamaIndex setup
    from llama_index.core import Settings, Document
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE)
        )
        print(f"[{ts()}] Created collection '{COLLECTION_NAME}'")
    else:
        count = client.count(COLLECTION_NAME).count
        print(f"[{ts()}] Collection '{COLLECTION_NAME}' exists — {count:,} vectors")

    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME,
                                     batch_size=BATCH_SIZE)
    pipeline = IngestionPipeline(
        transformations=[
            Settings.node_parser,
            Settings.embed_model,     # must be explicit — multiprocessing workers miss Settings
        ],
        vector_store=vector_store
    )

    tracker = load_tracker()
    print(f"[{ts()}] Tracker: {len(tracker)} existing entries\n")

    # Collect unprocessed summary JSONs
    print(f"[{ts()}] Scanning {RAG_ROOT} for summary files...")
    pending = []
    scanned = 0
    last_print = time.time()
    for fp in Path(RAG_ROOT).rglob("*.summary.json"):
        scanned += 1
        if str(fp) not in tracker:
            pending.append(fp)
        now = time.time()
        if now - last_print >= 5:
            print(f"[{ts()}] Scanned {scanned:,} files — {len(pending):,} pending so far")
            last_print = now

    print(f"[{ts()}] Found {len(pending):,} summary files to ingest\n")

    WAIT_MINS = 10

    while True:
        tracker = load_tracker()
        pending = []
        scanned = 0
        for fp in Path(RAG_ROOT).rglob("*.summary.json"):
            scanned += 1
            if str(fp) not in tracker:
                pending.append(fp)

        print(f"[{ts()}] Scan complete — {scanned:,} summary files, {len(pending):,} pending")

        if not pending:
            print(f"[{ts()}] Nothing to ingest. Waiting {WAIT_MINS} minutes before re-checking...")
            for remaining in range(WAIT_MINS * 60, 0, -30):
                mins, secs = divmod(remaining, 60)
                print(f"[{ts()}] Resuming in {mins}m {secs:02d}s...", end="\r")
                time.sleep(30)
            print()
            continue

        print("=" * 70)
        done = errors = 0
        session_start = time.time()
        total = len(pending)

        for i, fp in enumerate(pending, 1):
            try:
                summary_obj = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[{ts()}] [{i}/{total}] ERROR reading JSON: {fp.name} — {e}")
                tracker[str(fp)] = {"status": "error", "error": str(e), "processed_at": time.time()}
                save_tracker(tracker)
                errors += 1
                continue

            original_path = summary_obj.get("original_path", "")
            file_name     = summary_obj.get("file_name", fp.stem)

            print(f"[{ts()}] [{i}/{total}] {file_name}", end="  ", flush=True)

            try:
                text = build_document_text(summary_obj)

                doc = Document(
                    text=text,
                    metadata={
                        "original_path"  : original_path,
                        "rag_path"       : str(fp),
                        "file_name"      : file_name,
                        "file_extension" : summary_obj.get("file_extension", ""),
                        "document_type"  : summary_obj.get("document_type", ""),
                        "key_topics"     : ", ".join(summary_obj.get("key_topics", [])),
                        "entities"       : ", ".join(summary_obj.get("entities", [])),
                        "file_size_bytes": summary_obj.get("file_size_bytes", 0),
                        "file_modified"  : summary_obj.get("file_modified", ""),
                    },
                    id_=original_path or str(fp),
                )

                t0 = time.time()
                nodes = pipeline.run(documents=[doc], show_progress=False)
                elapsed = time.time() - t0

                print(f"— {len(nodes)} node(s)  {elapsed:.1f}s")

                tracker[str(fp)] = {
                    "status"       : "ok",
                    "original_path": original_path,
                    "nodes"        : len(nodes),
                    "processed_at" : time.time()
                }
                save_tracker(tracker)
                done += 1

            except Exception as e:
                print(f"— ERROR: {type(e).__name__}: {e}")
                tracker[str(fp)] = {
                    "status"       : "error",
                    "original_path": original_path,
                    "error"        : str(e),
                    "processed_at" : time.time()
                }
                save_tracker(tracker)
                errors += 1

        elapsed = time.time() - session_start
        avg = elapsed / max(done + errors, 1)
        print("\n" + "=" * 70)
        print(f"[{ts()}] Batch complete")
        print(f"  Ingested : {done:,}")
        print(f"  Errors   : {errors:,}")
        print(f"  Elapsed  : {elapsed:.0f}s  (avg {avg:.1f}s/doc)")
        print(f"  Vectors  : {client.count(COLLECTION_NAME).count:,}")
        print(f"  Waiting {WAIT_MINS} minutes before next scan...")
        print("=" * 70)

        for remaining in range(WAIT_MINS * 60, 0, -30):
            mins, secs = divmod(remaining, 60)
            print(f"[{ts()}] Next scan in {mins}m {secs:02d}s...", end="\r")
            time.sleep(30)
        print()


if __name__ == "__main__":
    main()
