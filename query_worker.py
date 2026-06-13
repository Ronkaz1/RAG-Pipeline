import time
import traceback
import logging
import pymssql
from datetime import datetime
from openai import OpenAI
from llama_index.core import VectorStoreIndex, Settings, StorageContext, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# ========================= CONFIG =========================
DB_SERVER   = "YOUR_SQL_SERVER"
DB_PORT = 1433
DB_NAME = "ged"
DB_USER     = "YOUR_DB_USER"
DB_PASSWORD = "YOUR_DB_PASSWORD"

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
EMBED_DIM = 768  # nomic-embed-text
COLLECTION_NAME = "bertha_docs"
OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_LLM_MODEL = "qwen2.5:3b"
POLL_INTERVAL = 3

GROK_API_KEY = "YOUR_GROK_API_KEY"
GROK_MODEL = "grok-3-mini"
# =========================================================

logging.basicConfig(
    filename="query_worker.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s: %(message)s"
)

def log(msg: str):
    print(msg, flush=True)

def log_error(msg: str, exc: BaseException = None):
    print(msg, flush=True)
    logging.error(msg)
    if exc:
        logging.error(traceback.format_exc())

grok_client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1", timeout=60.0)

def get_db_connection():
    return pymssql.connect(server=DB_SERVER, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, conn_properties='')

def call_grok(prompt: str, system: str = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = grok_client.chat.completions.create(
        model=GROK_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content.strip()

def is_no_data_response(answer: str) -> bool:
    check = call_grok(
        "Does the following response indicate that no relevant information was found, "
        "or that the system lacks enough data to give a meaningful answer? "
        "Reply with only YES or NO.\n\n"
        f"Response: {answer}"
    )
    return check.strip().upper().startswith("YES")

def ingest_to_rag(index, question: str, answer: str):
    doc = Document(
        text=answer,
        metadata={
            "source": "grok_fallback",
            "original_question": question[:500],
            "ingested_at": datetime.now().isoformat()
        }
    )
    parser = SentenceSplitter(chunk_size=800, chunk_overlap=100)
    nodes = parser.get_nodes_from_documents([doc])
    index.insert_nodes(nodes)
    log(f"   â†’ Ingested Grok answer into RAG ({len(nodes)} node(s))")

def setup_query_engine():
    log(f"[{datetime.now()}] Loading fresh Qdrant index...")

    Settings.embed_model = OllamaEmbedding(model_name=OLLAMA_EMBED_MODEL, embed_batch_size=50)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE)
        )

    vector_count = client.count(COLLECTION_NAME).count
    log(f"   Found {vector_count} vectors in collection")

    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

    llm = Ollama(
        model=OLLAMA_LLM_MODEL,
        request_timeout=120.0,
        temperature=0.3
    )

    query_engine = index.as_query_engine(
        llm=llm,
        similarity_top_k=8,
        response_mode="compact"
    )
    return query_engine, index, vector_count

log("Starting AI RAG Worker...")

query_engine = None
index = None

# ====================== MAIN LOOP ======================
while True:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT TOP 5 AI_Seq, Question, UserFullName
            FROM [dbo].[F_AI_Query]
            WHERE Done = 0 AND (Running = 0 OR Running IS NULL)
            ORDER BY AI_Seq ASC
        """)
        rows = cursor.fetchall()
        conn.close()

        if rows:
            log(f"[{datetime.now()}] New questions found â†’ Reloading index...")
            query_engine, index, vector_count = setup_query_engine()

        for row in rows:
            ai_seq = row[0]
            question = row[1]
            user = row[2] if row[2] else "User"

            log(f"\n[{datetime.now()}] Processing AI_Seq {ai_seq} | {user}: {question[:80]}...")

            conn = get_db_connection()
            conn.cursor().execute("UPDATE [dbo].[F_AI_Query] SET Running = 1 WHERE AI_Seq = %s", (ai_seq,))
            conn.commit()
            conn.close()

            answer = ""

            # Query local RAG first
            if query_engine:
                try:
                    rag_response = query_engine.query(question)
                    answer = str(rag_response)
                    log(f"   RAG answer: {answer[:300]}...")
                except Exception as e:
                    log_error(f"   âŒ RAG query error: {e}", e)
                    answer = ""

            # Check if RAG had nothing useful
            try:
                no_data = not answer or is_no_data_response(answer)
            except Exception as e:
                log_error(f"   âš  Could not classify RAG answer, assuming no data: {e}", e)
                no_data = True

            if no_data:
                log(f"   â†’ RAG had no relevant data. Querying Grok...")
                try:
                    grok_answer = call_grok(
                        question,
                        system=(
                            "You are an expert in the energy and oil industry. "
                            "All answers should be directed toward that domain. "
                            "Never open your response with phrases like 'In the oil and gas sector', "
                            "'In the energy industry', 'In the oil and gas industry', or any similar qualifier. "
                            "Do not reference the industry by name in your response at all â€” just answer directly. "
                            "Provide a complete, self-contained answer. "
                            "Do not ask follow-up questions or invite further conversation at the end of your response."
                        )
                    )
                    log(f"\n   â”€â”€ GROK ANSWER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")
                    log(f"   {grok_answer}")
                    log(f"   â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€\n")

                    if index:
                        ingest_to_rag(index, question, grok_answer)
                    answer = grok_answer

                except Exception as e:
                    log_error(f"   âŒ Grok error: {e}", e)
                    if not answer:
                        answer = f"Error retrieving answer: {str(e)}"
            else:
                log(f"   â†’ RAG had relevant data. Using local answer.")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE [dbo].[F_AI_Query]
                SET Answer = %s, Raw_Answer = %s, Done = 1, Running = 0
                WHERE AI_Seq = %s
            """, (answer[:8000], answer, ai_seq))
            conn.commit()
            conn.close()

            log(f"   âœ… Completed AI_Seq {ai_seq}")

        time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log("Shutting down.")
        break
    except BaseException as e:
        log_error(f"âŒ Main loop error: {type(e).__name__}: {e}", e)
        traceback.print_exc()
        err_str = str(e).lower()
        if "connection failed" in err_str or "adaptive server" in err_str or "operationalerror" in type(e).__name__.lower():
            log("   â†» DB connection error â€” retrying in 30s...")
            time.sleep(30)
        else:
            time.sleep(5)

log("Worker exited.")

