# 安裝說明

## Git Hook 設定（一次性）

在資料 repo 根目錄執行：

```bash
git config core.hooksPath .githooks
```

完成後，每次 commit 含有 `.bytes` 檔案時，差異摘要會自動出現在 commit 訊息視窗。

## 需求

| 項目 | 說明 |
|------|------|
| Python 3 | 有裝才會顯示摘要；沒有則靜默略過，不影響 commit |
| bytes_schemas.json | 放在 repo 根目錄，用 `schema_builder.html` 產生 |

## 工具說明

| 檔案 | 用途 |
|------|------|
| `schema_builder.html` | 上傳 Excel → 產生 `bytes_schemas.json` |
| `bytes_tester.html` | 上傳兩個 `.bytes` 進行差異比對 |
| `tools/bytes_diff_summary.py` | commit hook 呼叫的解析腳本 |
| `.githooks/prepare-commit-msg` | git hook 本體 |

## 使用流程

1. 用 `schema_builder.html` 上傳所有 Excel → 下載 `bytes_schemas.json` 放到 repo 根目錄
2. 執行 `git config core.hooksPath .githooks`
3. 之後修改 `.bytes` 並 `git add` → `git commit` 時自動顯示差異

## commit 訊息範例

```
[在這裡填寫 commit 說明]

# ══ .bytes 差異摘要 ══
# ── BattleLogStr_tc.bytes（Schema: BattleLogStr）──
#   修改 2 筆　新增 0 筆　刪除 1 筆
#   ~ ID=60001  Name: 舊文字 → 新文字
#   ~ ID=60002  Value: 100 → 150
#   - ID=59999
#
```

`#` 開頭的行不會進入最終 commit log，僅在填寫時供參考。
