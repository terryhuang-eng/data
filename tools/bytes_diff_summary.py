#!/usr/bin/env python3
"""
tools/bytes_diff_summary.py
為 prepare-commit-msg hook 產生 .bytes 差異摘要（以 # 開頭，不進入 commit log）

用法：python bytes_diff_summary.py <file1.bytes> [file2.bytes] ...
"""

import sys, os, struct, json, subprocess

# ── 工具 ──────────────────────────────────────────────
def norm_str(s):
    """正規化字串用於比對：小寫 + 去底線/連字號/空格"""
    return s.lower().replace('_', '').replace('-', '').replace(' ', '')

def git_show(ref_spec):
    """從 git 取得檔案原始內容，失敗回傳 None"""
    try:
        return subprocess.check_output(
            ['git', 'show', ref_spec],
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return None

def get_repo_root():
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return os.getcwd()

def find_schemas_json(repo_root):
    """找 bytes_schemas.json：腳本同層 → 上一層 → repo root"""
    script_dir    = os.path.dirname(os.path.abspath(__file__))
    script_parent = os.path.dirname(script_dir)
    candidates = [
        os.path.join(script_dir,    'bytes_schemas.json'),
        os.path.join(script_parent, 'bytes_schemas.json'),
        os.path.join(repo_root,     'bytes_schemas.json'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def find_schema(filename, schemas):
    """用關鍵字比對（正規化 contains）找對應 schema"""
    stem = norm_str(os.path.splitext(os.path.basename(filename))[0])
    for key, schema in schemas.items():
        if norm_str(key) in stem:
            return key, schema
    return None, None

# ── 型別別名 ──────────────────────────────────────────
TYPE_ALIAS = {
    'int8':'byte',  'uint8':'byte',  'u8':'byte',  'i8':'byte',
    'int16':'short','i16':'short',   'uint16':'ushort','u16':'ushort',
    'int32':'int',  'i32':'int',     'uint32':'uint', 'u32':'uint',
    'int64':'long', 'i64':'long',    'uint64':'ulong','u64':'ulong',
    'float32':'single','f32':'single','float64':'double','f64':'double',
    'boolean':'bool','str':'string',
}

# ── Debug 開關 ────────────────────────────────────────
import os as _dbg_os
DEBUG = _dbg_os.environ.get('BYTES_DEBUG', '0') == '1'

def dbg(*args):
    if DEBUG:
        print('[DEBUG]', *args, file=sys.stderr)

# ── reward 型別展開 ────────────────────────────────────
def expand_columns(columns):
    """將 type='reward' 的欄位展開為 3 欄：uint8 + int64 + int64"""
    result = []
    for col in columns:
        if col['type'].lower() == 'reward':
            name = col['name']
            dbg(f'expand reward: "{name}" → {name}(uint8) / {name}1(int64) / {name}2(int64)')
            result.append({'name': name,        'type': 'uint8'})
            result.append({'name': name + '1',  'type': 'int64'})
            result.append({'name': name + '2',  'type': 'int64'})
        else:
            result.append(col)
    return result

# ── 解析核心 ──────────────────────────────────────────
def parse_bytes(raw, schema):
    is_xor  = schema.get('isXor', False)
    data    = bytes(b ^ raw[0] for b in raw[1:]) if is_xor else raw
    columns = expand_columns(schema['columns'])

    str_compress_idx = next(
        (i for i, c in enumerate(columns) if c['name'] == '字串排縮'), None
    )
    is_decoded_idx = next(
        (i for i, c in enumerate(columns) if c['name'] == '是否解碼'), None
    )

    pos = 0

    def r_bool():
        nonlocal pos; v = data[pos]; pos += 1; return bool(v)
    def r_byte():
        nonlocal pos; v = data[pos]; pos += 1; return v
    def r_short():
        nonlocal pos; v = struct.unpack_from('<h', data, pos)[0]; pos += 2; return v
    def r_ushort():
        nonlocal pos; v = struct.unpack_from('<H', data, pos)[0]; pos += 2; return v
    def r_int():
        nonlocal pos; v = struct.unpack_from('<i', data, pos)[0]; pos += 4; return v
    def r_uint():
        nonlocal pos; v = struct.unpack_from('<I', data, pos)[0]; pos += 4; return v
    def r_long():
        nonlocal pos; v = struct.unpack_from('<q', data, pos)[0]; pos += 8; return v
    def r_ulong():
        nonlocal pos; v = struct.unpack_from('<Q', data, pos)[0]; pos += 8; return v
    def r_float():
        nonlocal pos; v = struct.unpack_from('<f', data, pos)[0]; pos += 4; return round(v, 6)
    def r_double():
        nonlocal pos; v = struct.unpack_from('<d', data, pos)[0]; pos += 8; return v

    def r_string(use_utf8=True):
        nonlocal pos
        n        = struct.unpack_from('<H', data, pos)[0]; pos += 2
        byte_len = n if use_utf8 else n * 2
        enc      = 'utf-8' if use_utf8 else 'utf-16-le'
        v        = data[pos:pos+byte_len].decode(enc, errors='replace')
        pos     += byte_len
        return v

    TYPE_MAP = {
        'bool':   r_bool,  'byte':  r_byte,  'short':  r_short, 'ushort': r_ushort,
        'int':    r_int,   'uint':  r_uint,  'long':   r_long,  'ulong':  r_ulong,
        'single': r_float, 'float': r_float, 'double': r_double,
    }

    data_count = struct.unpack_from('<i', data, pos)[0]; pos += 4
    dbg(f'data_count={data_count}, total_bytes={len(data)}, pos_after_header={pos}')
    dbg(f'columns({len(columns)}): ' + ', '.join(f'{c["name"]}:{c["type"]}' for c in columns))
    rows = []

    for row_idx in range(data_count):
        if pos >= len(data): break
        row          = []
        str_compress = None
        is_decoded   = None
        try:
            for ci, col in enumerate(columns):
                t = TYPE_ALIAS.get(col['type'].lower(), col['type'].lower())
                if t in TYPE_MAP:
                    val = TYPE_MAP[t]()
                elif t.startswith('dstring') or t == 'string':
                    # 是否解碼=0 → 未編碼，直接 UTF-8；否則看 字串排縮
                    if is_decoded is not None and is_decoded == 0:
                        use_utf8 = True
                    else:
                        use_utf8 = (str_compress != 0) if str_compress is not None else True
                    val = r_string(use_utf8)
                else:
                    raise ValueError(f'未知型別：{col["type"]}')
                if ci == str_compress_idx:
                    str_compress = int(val)
                if ci == is_decoded_idx:
                    is_decoded = int(val)
                row.append(val)
            rows.append(row)
        except Exception as e:
            dbg(f'row[{row_idx}] 解析失敗 pos={pos} col[{ci}]={col}: {e}')
            break

    return rows

# ── 比對 ──────────────────────────────────────────────
def diff_rows(rows_a, rows_b, key_cols=None):
    from collections import defaultdict

    if key_cols is None:
        key_cols = [0]

    def row_key(r):
        return '\t'.join(str(r[i]) for i in key_cols if i < len(r))

    def group(rows):
        m = defaultdict(list)
        for r in rows:
            m[row_key(r)].append(r)
        return m

    def try_col_insert(ra, rb):
        """若 rb = ra 插入一欄，回傳插入位置 k；否則 None。"""
        if len(rb) != len(ra) + 1:
            return None
        ra_s = [str(x) for x in ra]
        rb_s = [str(x) for x in rb]
        for k in range(len(rb)):
            if ra_s[:k] == rb_s[:k] and ra_s[k:] == rb_s[k+1:]:
                return k
        return None

    def try_col_delete(ra, rb):
        """若 rb = ra 刪除一欄，回傳刪除位置 k；否則 None。"""
        if len(ra) != len(rb) + 1:
            return None
        ra_s = [str(x) for x in ra]
        rb_s = [str(x) for x in rb]
        for k in range(len(ra)):
            if ra_s[:k] == rb_s[:k] and ra_s[k+1:] == rb_s[k:]:
                return k
        return None

    def try_col_shift(ra, rb, diff_cols):
        """
        同長度 row（bat 模式）：從第一個差異欄 k 開始，
        若 ra[k:N-1] == rb[k+1:N]（位移吻合），判定為欄位插入於 k。
        不要求 diff_cols 連續到 N-1，避免末欄偶然相同時誤判。
        """
        if not diff_cols or len(ra) != len(rb):
            return None
        N = len(ra)
        k = diff_cols[0]
        ra_s = [str(x) for x in ra]
        rb_s = [str(x) for x in rb]
        if N > k + 1 and ra_s[k:N-1] == rb_s[k+1:N]:
            return k
        return None

    # group with 1-indexed row numbers
    def group_with_idx(rows):
        m = defaultdict(list)
        for idx, r in enumerate(rows):
            m[row_key(r)].append((idx + 1, r))
        return m

    map_a = group_with_idx(rows_a)
    map_b = group_with_idx(rows_b)

    # 重複 key 集合（用於呼叫端決定是否顯示行號）
    dup_keys_b = {k for k, v in map_b.items() if len(v) > 1}
    dup_keys_a = {k for k, v in map_a.items() if len(v) > 1}

    added, removed, changed = [], [], []

    all_keys = list(dict.fromkeys([row_key(r) for r in rows_b] + [row_key(r) for r in rows_a]))

    for k in all_keys:
        a_entries = map_a.get(k, [])
        b_entries = map_b.get(k, [])
        for i, (row_num_b, rb) in enumerate(b_entries):
            if i < len(a_entries):
                row_num_a, ra = a_entries[i]
                diff_cols = [j for j in range(min(len(ra), len(rb))) if str(ra[j]) != str(rb[j])]
                if diff_cols:
                    ins = try_col_insert(ra, rb)
                    dlt = try_col_delete(ra, rb)
                    if ins is None and dlt is None:
                        ins = try_col_shift(ra, rb, diff_cols)
                    col_op = ('insert', ins) if ins is not None else ('delete', dlt) if dlt is not None else None
                    changed.append((ra, rb, diff_cols, col_op, row_num_b))
            else:
                added.append((rb, row_num_b))
        for i in range(len(b_entries), len(a_entries)):
            row_num_a, ra = a_entries[i]
            removed.append((ra, row_num_a))

    return added, removed, changed, dup_keys_b | dup_keys_a

# ── 顏色（ANSI，Windows 10+ cmd 支援）────────────────
import os as _os
_os.system('')          # 啟用 Windows cmd ANSI 支援
GREEN  = '\033[92m'
RED    = '\033[91m'
RESET  = '\033[0m'
STR_MAX = None          # 字串欄位不截斷

# ── 格式化輸出 ─────────────────────────────────────────
MAX_ROWS       = 5   # 每類最多顯示幾筆
INLINE_THRESH  = 3   # 異動欄位數 ≤ 此值時用單行，超過則多行

def format_diff(rel_path, key, schema, rows_a, rows_b):
    col_names = [c['name'] for c in expand_columns(schema['columns'])]
    key_cols  = schema.get('keyColumns', [0])
    added, removed, changed, dup_keys = diff_rows(rows_a, rows_b, key_cols)
    total = len(added) + len(removed) + len(changed)

    fname = os.path.basename(rel_path)
    lines = [f'# ── {fname}（Schema: {key}）──']

    if total == 0:
        lines.append('#   （內容無異動）')
        return lines

    lines.append(f'#   修改 {len(changed)} 筆　新增 {len(added)} 筆　刪除 {len(removed)} 筆')

    def row_key_str(row):
        return '\t'.join(str(row[i]) for i in key_cols if i < len(row))

    def fmt_key(row, row_num=None):
        parts = []
        for i in key_cols:
            if i < len(col_names) and i < len(row):
                parts.append(f'{col_names[i]}={row[i]}')
        s = '  '.join(parts)
        if row_num is not None and row_key_str(row) in dup_keys:
            s += f'（第{row_num}筆）'
        return s

    # 修改列
    for ra, rb, diff_cols, col_op, row_num_b in changed:
        k_str = fmt_key(ra, row_num_b)
        if col_op:
            kind, k = col_op
            col_name = col_names[k] if k < len(col_names) else f'col_{k}'
            if kind == 'insert':
                lines.append(GREEN + f'#   ~ {k_str}  ＋新增欄位 {col_name}（值：{rb[k]}）' + RESET)
            else:
                lines.append(RED + f'#   ~ {k_str}  －刪除欄位 {col_name}（舊值：{ra[k]}）' + RESET)
            continue
        cn_list = [(col_names[ci] if ci < len(col_names) else f'col_{ci}') for ci in diff_cols]
        if len(diff_cols) <= INLINE_THRESH:
            parts = [k_str]
            for ci, cn in zip(diff_cols, cn_list):
                parts.append(f'{cn}: {ra[ci]} → {rb[ci]}')
            lines.append('#   ~ ' + '  '.join(parts))
        else:
            lines.append(f'#   ~ {k_str}（{len(diff_cols)} 欄變更）')
            for ci, cn in zip(diff_cols[:4], cn_list[:4]):
                lines.append(f'#       {cn}: {ra[ci]} → {rb[ci]}')
            if len(diff_cols) > 4:
                lines.append(f'#       …還有 {len(diff_cols) - 4} 欄')

    # 新增列（綠色，列出所有欄位）
    for r, row_num_b in added:
        parts = []
        for ci, cn in enumerate(col_names):
            if ci >= len(r): break
            parts.append(f'{cn}={str(r[ci])}')
        suffix = f'（第{row_num_b}筆）' if row_key_str(r) in dup_keys else ''
        lines.append(GREEN + '#   + ' + '  '.join(parts) + suffix + RESET)

    # 刪除列（紅色，只顯示 key）
    for r, row_num_a in removed:
        lines.append(RED + f'#   - {fmt_key(r, row_num_a)}' + RESET)

    return lines

# ── 主程式 ────────────────────────────────────────────
def main():
    filepaths = sys.argv[1:]
    if not filepaths:
        sys.exit(0)

    repo_root    = get_repo_root()
    schemas_path = find_schemas_json(repo_root)
    if not schemas_path:
        sys.exit(0)

    with open(schemas_path, 'r', encoding='utf-8') as f:
        schemas = json.load(f)

    output_lines = ['#', '# ══ .bytes 差異摘要 ══']
    any_output   = False

    for filepath in filepaths:
        try:
            rel = os.path.relpath(filepath, repo_root).replace('\\', '/')
        except ValueError:
            rel = filepath.replace('\\', '/')

        key, schema = find_schema(filepath, schemas)
        if not schema:
            output_lines.append(f'# {os.path.basename(filepath)}: 找不到對應 Schema')
            continue

        staged_raw = git_show(f':{rel}')
        head_raw   = git_show(f'HEAD:{rel}')

        try:
            rows_b = parse_bytes(staged_raw, schema) if staged_raw else []
            rows_a = parse_bytes(head_raw,   schema) if head_raw   else []
        except Exception as e:
            output_lines.append(f'# {os.path.basename(filepath)}: 解析失敗（{e}）')
            continue

        lines = format_diff(rel, key, schema, rows_a, rows_b)
        output_lines.extend(lines)
        any_output = True

    if any_output:
        output_lines.append('#')
        print('\n'.join(output_lines))

if __name__ == '__main__':
    main()
