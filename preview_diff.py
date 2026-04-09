#!/usr/bin/env python3
"""
preview_diff.py
雙擊 preview_diff.bat 執行，顯示目前已暫存 .bytes 檔案的差異摘要
"""
import subprocess, sys, os

repo_root = os.path.dirname(os.path.abspath(__file__))

result = subprocess.run(
    ['git', 'diff', '--cached', '--name-only', '--diff-filter=AM'],
    capture_output=True, text=True, cwd=repo_root
)
files = [f.strip() for f in result.stdout.split('\n') if f.strip().endswith('.bytes')]

if not files:
    print('目前沒有暫存的 .bytes 檔案。')
    print('請先在 Fork 中 Stage 要 commit 的 .bytes 檔案，再執行此工具。')
    sys.exit(0)

script = os.path.join(repo_root, 'tools', 'bytes_diff_summary.py')
subprocess.run([sys.executable, script] + files)
