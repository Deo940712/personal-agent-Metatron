# part-011-slice-001 — advisor 降頻 + world-diff 知識訊號(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

校準閉環收尾(todo 5)+ part-008↔009 接線(todo 6)。

## Delivered

- **todo 5** `core/advisor.py`:`push_candidates` 加 `_is_downthrottled`——某
  dedup_key 有**穩定** ignore 的 `advice_pref__<dedup>` facet → 停推(降頻)。
  保守:僅 stable ignore 降頻;provisional/accept 照常推。校準閉環閉合
  (record_feedback 累積 → push 讀取)。(tests/test_advisor_push.py:+4)
- **todo 6** `core/advisor.py`:WorldDiff 加 `new_knowledge` 欄位 +
  `_count_new_knowledge`(掃 external_untrusted inbox,**count-only**——只數量、
  不讀內文,防注入);observe/tick 加 vault 參數;reflect prompt 告知數量(不餵
  untrusted 內文);quiet 納入 new_knowledge。(tests/test_advisor.py:+3)

## Verification

- Unit: `python -m pytest tests/test_advisor.py tests/test_advisor_push.py tests/test_advisor_reflect.py -q` → 47 passed
- Regression: `python -m pytest tests/ -q` → **826 passed**(基線 820 + 6)
- Manual QA(實跑):穩定 ignore 的 dedup_key 被 push 排除、accept 照推;
  scout 抓一則 → observe().new_knowledge=1、quiet=False。

## 防注入(硬規則)

new_knowledge 是 **count-only**——只回數量;untrusted note 內文永不進 advice/
reflect prompt。「你有 N 則抓來的資料待檢視」的信號,不讀內容。
