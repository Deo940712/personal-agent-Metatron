# part-011 DESIGN — 收尾接線 + 文件 + 回歸測試（closing-loop）

> 注意：此 part-011 是「收尾接線」，與 PLAN.md 表中 backlog 的 part-011
> (MiroFish adapter) 不同——後者仍 gate-locked（backlog-028，無需求不做）。
> 本 part 不新增功能，只補既有 part 之間留待後續的接線 + 文件漂移 + 測試缺口。

## Goal

把四個規劃 part（007/008/009/010）之間「留待後續」的接線補齊，讓系統真正閉環；
同步文件到最新（含 part-010）；補記憶檢索品質回歸測試。**不新增 part/表/job。**

計畫權威：`.omo/plans/next-phase-wiring-qa.md`（Prometheus，已 gap 分析）。

## Non-goals

- 不新增 part / DB 表 / 排程 job（routine 掛既有 consolidate 尾端）
- 不繞過 writer 的任何 facet/state 寫入
- 不碰 gate-locked backlog：MiroFish(028)、AgentSpec(029)、librarian(017)、
  rerank(025)、per-category decay(026)
- 不重測 Task Capsule B（MEM-17：A 無可重現失敗）
- 不做真環境 QA（LLM key / Discord / VPS 仍 blocked）
- 不做 advisor 自動觸發情境演練（part-010 明列後續）
- 不改 vendored crowd-scenario 原始碼

## Chosen Design

### 核心根因修復
`facets.extract_routine` 是死程式碼（零 caller）。根因：完成 task/schedule 時只寫
`state_change` 事件，沒寫 `completed` 事件，而 `advisor._routine_deviation`（讀
`action='completed'`）與 `extract_routine`（需完成記錄）都餓死。補一個 `completed`
事件同時修好三條斷鏈。

### 關鍵耦合（已驗證 core/health.py）
`completed` 事件是普通 alive 事件——會 decay → trash → 被蒸餾成 episodic 筆記。
因此：
- routine producer 必須 **window-read**（alive + trash），與蒸餾**同跑**（掛
  consolidate 尾端，不獨立 job——獨立 job 會跟代謝賽跑）
- routine facet 的 evidence_ids 指向 **transcript source_id**（durable，事件歸檔後
  仍可回水），不指向短暫的事件列
- 接受 completed 事件也成為 episodic 筆記（不同記憶層：episodic=「發生什麼」，
  routine facet=「模式」；非重複計算）

## Verification Targets

- done → completed 事件 + transcript source_id；cancel 不寫 completed
- extract_routine 有 caller；完成足量 → routine facet（durable transcript evidence）
- advisor routine-deviation 讀真 completed 事件端到端
- advisor push 降頻：穩定 ignore 的 dedup_key 不再推
- world-diff new_knowledge：scout untrusted inbox 計數（count-only，防注入）
- 文件反映 part-010 + 三接線；CheckMemoryDocs 綠
- golden queries 回歸（15 筆記 / 20 斷言，確定性）

## Unit Test Strategy

pytest，全程 TDD；LLM mock；routine/advisor 走真 writer 路徑測；golden queries
不打真 LLM/網路（測 retrieve.search 層）。

## Manual QA Strategy

排程 `--job consolidate`（mock LLM）確認 routine facet 路徑觸發；完成幾件事
（偏離作息）→ consolidate → advisor.observe 偵測偏離。
