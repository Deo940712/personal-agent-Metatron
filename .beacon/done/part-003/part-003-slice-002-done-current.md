# DONE: part-003-slice-002 ltm.py + consolidate 蒸餾管線

Completed: 2026-07-13
Design authority: `.beacon/parts/part-003/DESIGN.md`;技術規格 docs/MEMORY-zh.md §5

## 交付物

- `core/ltm.py` — vault 寫入層:init_vault(idempotent,五子目錄 + INDEX.md 種子)、
  controlled_tags(INDEX 為執行期真相)、write_note(frontmatter 組裝、
  YYYYMMDD-slug 防撞 -2/-3、Windows 非法檔名字元清洗)、registry 維護/解析
  (壞行跳過)、read_note(壞 frontmatter → None 不炸全庫)
- `agents/consolidator.md` — 蒸餾契約:kind(episodic/preference)、
  「source_event_ids 一個都不能虛構」、confidence 誠實給分;2 個 few-shot
  (含空 groups 例)
- `core/consolidate.py` — 全管線:decay → to_trash → due → 按天分組(≤50/組)
  → LLM → **五條欄位級驗證(逐組跳過)** → 寫筆記(帶 source_ids)→
  mark_archived;LLM 失敗該天留 trash 下輪重試
- `core/agent.py` 加 `--job consolidate`(agent_runs 記錄;延遲 import)
- 測試:test_ltm.py(8)+ test_consolidate.py(19)

## Verification Evidence

Automated commands:
- `python -m pytest tests/test_ltm.py tests/test_consolidate.py -q` → **27 passed**
- `python -m pytest tests/ -q` → **143 passed**(116 既有迴歸不壞)

覆蓋:vault init/roundtrip/撞號/Windows 檔名/壞檔防禦;全管線(筆記+archived+
**回水閉環:沿 source_ids 讀回 transcript 原文**);preference → agent/profile/;
**驗證五條 × 12 boundary 案例**(kind 幻覺/詞彙表外 tag/虛構 source_ids/bool 偽裝/
低 confidence/501 字 summary…)每個都:不寫筆記 + events 留 trash + 記 rejected;
逐組跳過(同批一好一壞);LLM 整晚失敗不丟資料;分組上限;--job 接線。

Manual QA:
- item: 目檢 vault 產出(等效:腳本印出 INDEX.md + 筆記全文)
- status: passed
- evidence: INDEX registry 一行描述正確;筆記 frontmatter 含 id/source/period/
  source_ids(list)/distilled_at/model/tags/summary,格式為合法 YAML,
  Obsidian 可直接開啟

Incidents: none

## 設計筆記(移交 slice-003)

- B7(db=None footgun):consolidate.run 的 vault/transcript_dir 已必填化
  (config fallback 只在 run 入口);完全移除 stm 層 None 預設仍留待評估——
  CLI 的 --db None → config 是刻意設計,維持現狀,B7 標 mitigated 即可
- write_note 的 summary 進 registry 截 120 字——index-first 的資料源
- 中文 slug 保留(Obsidian 友善);純符號標題 fallback 'note'
