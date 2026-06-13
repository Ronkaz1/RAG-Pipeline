import os
from pathlib import Path
from datetime import datetime

ROOT = r"\\bigbertha\Data\Companies_Clients"

def folder_size(path: Path):
    total = 0
    file_count = 0
    try:
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
                    file_count += 1
            except OSError:
                pass
    except OSError:
        pass
    return total, file_count

def fmt_size(b):
    if b >= 1_073_741_824: return f"{b/1_073_741_824:>9.2f} GB"
    if b >= 1_048_576:     return f"{b/1_048_576:>9.1f} MB"
    return                        f"{b/1_024:>9.1f} KB"

def main():
    root = Path(ROOT)
    if not root.exists():
        print(f"Cannot reach: {ROOT}")
        return

    print(f"Scanning: {ROOT}")
    print(f"Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    folders = sorted([f for f in root.iterdir() if f.is_dir()])
    results = []

    for i, folder in enumerate(folders, 1):
        print(f"  [{i}/{len(folders)}] Scanning {folder.name}...", end="\r")
        size, count = folder_size(folder)
        results.append((folder.name, size, count))

    results.sort(key=lambda x: x[1], reverse=True)

    total_size  = sum(r[1] for r in results)
    total_files = sum(r[2] for r in results)

    W = 72
    print(" " * W)  # clear the progress line
    print("=" * W)
    print(f"  {'Folder':<38}  {'Size':>9}   {'Files':>7}   {'%':>5}")
    print("  " + "-" * (W - 2))

    for name, size, count in results:
        pct = size / total_size * 100 if total_size else 0
        print(f"  {name:<38}  {fmt_size(size)}   {count:>7,}   {pct:>5.1f}%")

    print("  " + "-" * (W - 2))
    print(f"  {'TOTAL':<38}  {fmt_size(total_size)}   {total_files:>7,}   100.0%")
    print("=" * W)
    print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
