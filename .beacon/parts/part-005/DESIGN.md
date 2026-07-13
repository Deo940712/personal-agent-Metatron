# part-005 DESIGN

## Goal

coding_tracker:三個唯讀掃描器(git / beacon / opencode)確定性收集 vibe coding
進度 → LLM 綜合每專案一句 → `project_update` 提案 → writer → projects 表。
完成後:`--job track` 自動更新所有已註冊專案的 phase/blockers/next_action。

## Non-goals

- 寫入任何被掃描的 repo / .beacon / opencode.db(全部唯讀,ARCHITECTURE §3.3 鐵律)
- MCP 暴露(part-006;本 part 的 octools 即其 dev_status 的資料層,提前落地)
- 自動發現專案(只掃 projects 表中有 repo_path 的——使用者顯式註冊)

## 探勘實證(2026-07-13)

| # | 發現 | 設計後果 |
|---|---|---|
| P1 | opencode.db `session.time_updated` 是 **epoch 毫秒**(13位) | octools 統一除 1000 轉秒(全系統 UTC epoch 秒慣例) |
| P2 | `session.directory` 用正斜線(`C:/Users/...`),與 Windows `repo_path` 反斜線不同 | 路徑比對用 `Path.resolve()` 正規化,不做字串比對 |
| P3 | `session.model` 是 JSON 字串;`title` 有意義(如「Pi Agents 架構規劃與設計」) | 摘要用 title + agent + time;model 解析 JSON 失敗容忍 |
| P4 | `todo` 表有 content/status/position,關聯 session_id | 進度訊號:最新 session 的 todo 完成率 |
| P5 | `part.data` type=text 含對話全文 | coding_tracker **不讀對話全文**(太重);session_tail 留給 part-006 MCP |
| P6 | git:`rev-list --count @{u}..HEAD` 取未推送數;無 upstream 時報錯 | subprocess 容錯:報錯 → unpushed=None |
| P7 | beacon:CURRENT.md 格式為 `Part:/Slice:/Status:` 行 或 `Status: planning-only` | parser 兩種形態都要接;缺 .beacon → None(非錯誤) |

## Chosen Design

### 模組

| 檔案 | 職責 |
|---|---|
| `core/octools.py` | opencode.db 唯讀讀取器(`mode=ro` URI):`recent_sessions(directory, limit)` → [{id,title,agent,updated_at(秒)}];`session_todos(session_id)` → 完成率統計。**同時是 part-006 dev_status/session_tail 的資料層** |
| `core/scanners.py` | `git_scan(repo_path)` → {last_commit_at, last_message, recent[], unpushed, branch};`beacon_scan(repo_path)` → {status, part, slice, plan_summary} 或 None。subprocess/檔案讀取全容錯(壞 repo → 部分結果+error 欄位) |
| `agents/coding_tracker.md` | 純函數契約:輸入=每專案三源掃描 JSON;輸出=每專案 {name, phase, blockers[], next_action, confidence};規則:phase 以 beacon CURRENT 為最高權威、git/opencode 為輔證;無資料的專案誠實回報 |
| `core/track.py` | 管線:projects 表撈有 repo_path 的 → 三源掃描(確定性)→ LLM 批次綜合 → `project_update` 提案 → writer 驗證落地 → 統計 |
| writer 擴充 | `project_update` proposal_type:validate(phase 字串/blockers list/next_action)+ 落地 = stm.project_set(upsert 只更新給定欄位) |
| `core/agent.py` | `--job track` |

### 資料流(ARCHITECTURE §3.3 的實作)

```
projects 表(repo_path 非空)
  → 每專案:git_scan + beacon_scan + octools.recent_sessions(確定性,全唯讀)
  → LLM 一批綜合(≤10 專案/批)→ project_update 提案
  → writer.precheck(proposals 驗證)→ 落地 projects 表(免確認——
    §3.2 自動放行層:projects 是 Working State 快取,錯了下輪自動修正,
    且來源是唯讀掃描非使用者指令)
  → events 記 state_change
```

### project_update 免確認的理由(記入 §3.1 規則)

schedule/task 寫入需確認因為錯誤有真實代價(錯的提醒時間)。project_update
是「從唯讀訊號推導的快取」:錯了無副作用、下輪 track 自動修正、使用者在
`proj` 指令看到即可人工糾正(stm.project_set 手動優先)。

## Verification Targets

- octools:毫秒轉秒、directory 正規化比對、壞 db 路徑容錯、todo 完成率
- scanners:git 正常/無 upstream/非 git 目錄;beacon 正常/planning-only/缺 .beacon
- track(mock LLM):全管線、LLM 幻覺專案名拒絕、部分掃描失敗仍處理其餘專案
- writer:project_update 驗證(phase/blockers/next 型別)+ 落地 upsert
- 手動 QA:對本專案自己跑 `--job track`(真三源,mock LLM)→ projects 表有本專案

## Unit Test Strategy

pytest;LLM mock;git 用 tmp repo 實測(git init + commit);opencode.db 用
tmp 建同 schema 假庫(不碰真 db);beacon 用 tmp 假 CURRENT.md。

## Risks

- opencode.db schema 是內部實作,版本升級可能變(backlog-013 已記)——octools
  容錯:表不存在/欄位缺 → 空結果 + events 記 warning,不 crash
- 真 opencode.db 被鎖(OpenCode 運行中)——WAL 模式併發讀 OK(part-006 探勘已證),
  仍加 timeout + 容錯

## Open Questions

無。
