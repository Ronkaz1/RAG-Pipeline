import tkinter as tk
import subprocess
import threading
import json
import os

# (label, bat, script_to_detect)  — None detect = never green (one-shot commands)
SCRIPTS = [
    ("Start Services (Qdrant + Ollama)",  "start_services.bat",   None),
    ("─" * 40,                            None,                    None),
    ("Pipeline  (Summarizer + Ingester)", "run_pipeline.bat",      "pipeline.py"),
    ("Summarizer only",                   "run_summarizer.bat",    "summarizer.py"),
    ("RAG Ingester only",                 "run_rag_ingester.bat",  "rag_ingester.py"),
    ("─" * 40,                            None,                    None),
    ("Query Worker v2  (RAG + doc load)", "run_worker_v2.bat",     "query_worker_v2.py"),
    ("Query Worker  (original)",          "run_worker.bat",         "query_worker.py"),
    ("─" * 40,                            None,                    None),
    ("Dashboard  (summarization)",        "run_dashboard.bat",     "dashboard.py"),
    ("Retry Timed-Out Files",             "run_retry.bat",         "retry_timed_out.py"),
    ("Folder Sizes",                      "run_folder_sizes.bat",  "folder_sizes.py"),
]

BASE            = r"D:\Code\AI"
SUMMARY_TRACKER = r"D:\RAG\_summary_tracker.json"
INGEST_TRACKER  = r"D:\RAG\_ingest_tracker.json"
TOTAL_DOCS      = 407_106
STATS_REFRESH   = 30   # seconds
PROCESS_REFRESH = 5    # seconds

# colours
C_BG       = "#1e1e1e"
C_BTN      = "#2d2d2d"
C_BTN_HVR  = "#3a3a3a"
C_BTN_RUN  = "#1a3a1a"
C_BTN_RHVR = "#1f4a1f"
C_FG       = "#d4d4d4"
C_FG_RUN   = "#4ec94e"


def launch(bat):
    subprocess.Popen(
        f'start "" cmd /k "{os.path.join(BASE, bat)}"',
        shell=True, cwd=BASE
    )


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_running_scripts() -> set:
    """Return set of script basenames currently running under python/pythonw."""
    try:
        result = subprocess.run(
            'wmic process where "name=\'python.exe\' or name=\'pythonw.exe\'" get commandline',
            capture_output=True, text=True, shell=True, timeout=5
        )
        text = result.stdout.lower()
        return {word.strip('"\'') for word in text.split()
                if word.strip('"\'').endswith(".py")}
    except Exception:
        return set()


# ── Build UI ──────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("RAG Pipeline")
root.resizable(False, False)
root.configure(bg=C_BG)

tk.Label(root, text="RAG Pipeline Menu", font=("Segoe UI", 13, "bold"),
         bg=C_BG, fg="#ffffff", pady=10).pack()

buttons = []   # (btn_widget, detect_script)

for label, bat, detect in SCRIPTS:
    if bat is None:
        tk.Label(root, text=label, bg=C_BG, fg="#444444",
                 font=("Consolas", 8)).pack(fill="x", padx=20)
    else:
        btn = tk.Button(
            root, text=label,
            font=("Segoe UI", 10),
            bg=C_BTN, fg=C_FG,
            activebackground="#0e639c", activeforeground="#ffffff",
            relief="flat", cursor="hand2",
            padx=16, pady=6,
            command=lambda b=bat: launch(b)
        )
        btn.pack(fill="x", padx=20, pady=2)

        def make_hover(w, d):
            def on_enter(e):
                running = w.cget("bg") in (C_BTN_RUN, C_BTN_RHVR)
                w.config(bg=C_BTN_RHVR if running else C_BTN_HVR)
            def on_leave(e):
                running = w.cget("bg") in (C_BTN_RUN, C_BTN_RHVR)
                w.config(bg=C_BTN_RUN if running else C_BTN)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        make_hover(btn, detect)
        buttons.append((btn, detect))


def refresh_buttons():
    running = get_running_scripts()
    for btn, detect in buttons:
        if detect and detect.lower() in running:
            btn.config(bg=C_BTN_RUN, fg=C_FG_RUN)
        else:
            # Only reset if not currently hovered (bg not the hover shade)
            if btn.cget("bg") not in (C_BTN_HVR, C_BTN_RHVR):
                btn.config(bg=C_BTN, fg=C_FG)
    root.after(PROCESS_REFRESH * 1000, refresh_buttons)


# ── Stats panel ───────────────────────────────────────────────────────────────
tk.Frame(root, bg="#333333", height=1).pack(fill="x", padx=20, pady=(12, 0))

stats_frame = tk.Frame(root, bg=C_BG)
stats_frame.pack(fill="x", padx=24, pady=(6, 12))

STAT_FONT = ("Consolas", 9)
STAT_FG   = "#888888"

lbl_fs  = tk.Label(stats_frame, text=f"File system :  {TOTAL_DOCS:,}", font=STAT_FONT, bg=C_BG, fg=STAT_FG, anchor="w")
lbl_sum = tk.Label(stats_frame, text="Summarized  :  ...",              font=STAT_FONT, bg=C_BG, fg=STAT_FG, anchor="w")
lbl_ing = tk.Label(stats_frame, text="Ingested    :  ...",              font=STAT_FONT, bg=C_BG, fg=STAT_FG, anchor="w")

lbl_fs.pack(fill="x")
lbl_sum.pack(fill="x")
lbl_ing.pack(fill="x")


def get_stats():
    summary  = load_json(SUMMARY_TRACKER)
    ingested = load_json(INGEST_TRACKER)
    n_sum = sum(1 for v in summary.values()  if v.get("status") == "ok")
    n_ing = sum(1 for v in ingested.values() if v.get("status") == "ok")
    lbl_sum.config(text=f"Summarized  :  {n_sum:,}")
    lbl_ing.config(text=f"Ingested    :  {n_ing:,}")
    root.after(STATS_REFRESH * 1000, lambda: threading.Thread(target=get_stats, daemon=True).start())


root.after(500,  lambda: threading.Thread(target=get_stats,     daemon=True).start())
root.after(1000, refresh_buttons)

root.mainloop()
