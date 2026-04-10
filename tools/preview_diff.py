#!/usr/bin/env python3
"""
preview_diff.py
雙擊 preview_diff.bat 執行，顯示目前已暫存 .bytes 檔案的差異摘要
"""
import subprocess, sys, os

# git repo 根目錄（不論本檔放在 repo 內任何位置）
try:
    git_root = subprocess.check_output(
        ['git', 'rev-parse', '--show-toplevel'],
        stderr=subprocess.DEVNULL, text=True
    ).strip()
except Exception:
    git_root = os.path.dirname(os.path.abspath(__file__))

result = subprocess.run(
    ['git', 'diff', '--cached', '--name-only', '--diff-filter=AM'],
    capture_output=True, text=True, cwd=git_root
)
# 轉為絕對路徑
files = [
    os.path.join(git_root, f.strip())
    for f in result.stdout.split('\n')
    if f.strip().endswith('.bytes')
]

if not files:
    print('目前沒有暫存的 .bytes 檔案。')
    print('請先在 Fork 中 Stage 要 commit 的 .bytes 檔案，再執行此工具。')
    sys.exit(0)

# bytes_diff_summary.py 與本檔同層
script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bytes_diff_summary.py')
subprocess.run([sys.executable, script] + files)
