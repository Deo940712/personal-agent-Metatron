# part-008-slice-000 — watchlist 表 + allowlist + research query 建構(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

DB1 第十一表 `watchlist` + allowlist config + 確定性 research query 建構器 +
watchlist 到期判定。全確定性、無網路、無 LLM。

## Delivered

- `core/stm.py`:`watchlist` DDL(topic/source_url/interval_days/last_checked_at/
  state[active|paused];UNIQUE topic+url)+ CRUD(watchlist_add/list/set_state/
  touch_checked)+ CLI `watchlist add|list|pause|resume`
- `config.py`:SCOUT_ALLOWLIST_DOMAINS(arxiv/github/HN 起步)+ SCOUT_MAX_PER_RUN=5 +
  SCOUT_MIN_INTERVAL_DAYS=1
- `core/scout.py`:
  - `is_allowed_url`:網域 allowlist fail-closed(只准 http(s)+清單內含子網域;
    子字串攻擊 arxiv.org.evil.com 拒絕;空清單全拒)
  - `build_query`:確定性查詢字串(不呼叫 LLM)
  - `due_watchlist`:到期 active 主題(來源不在 allowlist 一律排除;下限守衛)
- `tests/test_scout.py`:22 tests(allowlist 准/拒/子網域/大小寫/子字串攻擊/
  非法 scheme/空清單/config 預設、build_query 確定性、watchlist CRUD+UNIQUE+
  pause/resume、due 判定+interval+min_interval+排除 paused/非 allowlist)

## Verification

- Unit: `python -m pytest tests/test_scout.py tests/test_schema.py -q` → 38 passed
- Regression: `python -m pytest tests/ -q` → **757 passed**(基線 735 + 22)
- Manual QA(實跑):10 表舊庫 → `init` idempotent 升級 11 表;allowlist 正確
  准 arxiv+子網域、拒子字串攻擊網域+非法 scheme;watchlist add/list CLI。

## Notes

- allowlist 子字串攻擊防禦:`host == allowed or host.endswith("." + allowed)`
  ——arxiv.org.evil.com 的 host 不等於也不以 ".arxiv.org" 結尾,拒絕。
- 網路抓取、external_untrusted 標籤、curator 隔離框是 slice-001;本 slice 零網路。
