# part-004.5 Verification Report

Completed: 2026-07-13
Slices: 3/3（主題連續性蒸餾 / supersede 執行 / RRF 融合）

## Final verification

- `python -m pytest tests/ -q` → **280 passed**（254 → 280，+26）

## Phase 4.5 Gate

| 條件 | 結果 |
|---|---|
| 主題 trace 連結生效（跨天同 topic 雙向 related） | ✅（30 天窗、冪等、preference 隔離） |
| supersede 落地（舊筆記標 superseded_by，雙側保留） | ✅（驗證七條、U2 不對稱漏洞修復） |
| RRF 融合排序正確且強命中短路 | ✅（手算公式驗證、embed_fn 零呼叫斷言） |

## Audit gate 記錄

- slice-001：4 探針全 clean（30/31 字邊界、preference 隔離、同批連結、冪等）
- slice-002：**U2 真漏洞**（episodic 帶 supersedes 繞過驗證直接 mark——驗證與
  執行不對稱）當場修 + regression
- slice-003：5 探針全 clean（stage 無邏輯漣漪、token 語意、強命中完整性）

## 論文對應（backlog 022/023/024 全部 resolved）

- Membox 輕量版：topic 欄位 + 跨天 related（不引入 Topic Loom 圖結構）
- Mneme：雙側保留 + 既有 profile 注入 + recall superseded_by co-surface
- Cognis/RRF：k=60 標準融合 + 強命中零成本短路保留

## 已知限制（DESIGN 記錄）

- topic 自由文字，同義不同字不連結（精確 clustering 需 embedding，過度工程不做）
- supersede 鏈只查一層（深鏈場景 recall 契約未要求遞迴）
