import os
import json
import time
import sys
import threading
from pathlib import Path
from datetime import datetime

# ========================= CONFIG =========================
SOURCE_FOLDER   = r"\\bigbertha\Data\Companies_Clients"
SUMMARY_TRACKER = r"D:\RAG\_summary_tracker.json"
INGEST_TRACKER  = r"D:\RAG\_ingest_tracker.json"
REFRESH_SECS    = 10
# =========================================================

SUPPORTED_EXT = {'.pdf', '.txt', '.md', '.docx', '.doc', '.pptx', '.ppt',
                 '.xlsx', '.xls', '.csv', '.html', '.htm'}

_scan_lock         = threading.Lock()
_scan_total        = 0
_scan_done         = False
_scan_count_so_far = 0


def background_scan():
    global _scan_total, _scan_done, _scan_count_so_far
    count = 0
    for fp in Path(SOURCE_FOLDER).rglob("*"):
        if fp.is_file() and fp.suffix.lower() in SUPPORTED_EXT:
            count += 1
            _scan_count_so_far = count
    with _scan_lock:
        _scan_total = count
        _scan_done  = True


def load_json(path):
    for _ in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            time.sleep(0.2)
    return {}


def bar(pct, width=60):
    filled = round(width * pct / 100)
    return '█' * filled + '░' * (width - filled)


def render(summary_tracker, ingest_tracker):
    with _scan_lock:
        total      = _scan_total
        scan_ready = _scan_done

    W = 68

    # A file is "done" if it appears in either tracker
    # Ingest tracker keys are rag_paths; get original_paths from values
    ingested_originals = {
        v.get("original_path")
        for v in ingest_tracker.values()
        if v.get("original_path")
    }
    done = set(summary_tracker.keys()) | ingested_originals
    n_done = len(done)

    os.system('cls')
    print('═' * W)
    print(f'  SUMMARIZATION DASHBOARD     {datetime.now().strftime("%Y-%m-%d  %H:%M:%S")}')
    print('═' * W)
    print()

    if not scan_ready:
        total_display = _scan_count_so_far or 1
        remaining = max(0, total_display - n_done)
        pct_done  = n_done / total_display * 100
        print(f'  Scanning source folder... {_scan_count_so_far:,} files found so far')
        print()
        print(f'  Processed  : {n_done:,}')
        print(f'  Remaining  : ~{remaining:,}')
        print()
        print(f'  {bar(pct_done, W - 4)}  {pct_done:.2f}%')
    else:
        remaining = max(0, total - n_done)
        pct_done  = n_done / total * 100 if total else 0
        pct_rem   = 100 - pct_done

        print(f'  Total      : {total:,}')
        print(f'  Processed  : {n_done:,}')
        print(f'  Remaining  : {remaining:,}   ({pct_rem:.2f}%)')
        print()
        print(f'  {bar(pct_done, W - 4)}  {pct_done:.2f}%')

    print()
    print(f'  Auto-refreshing every {REFRESH_SECS}s — Ctrl+C to exit')
    print('═' * W)


def main():
    once = '--once' in sys.argv

    threading.Thread(target=background_scan, daemon=True).start()

    while True:
        render(load_json(SUMMARY_TRACKER), load_json(INGEST_TRACKER))
        if once:
            break
        time.sleep(REFRESH_SECS)


if __name__ == '__main__':
    main()
