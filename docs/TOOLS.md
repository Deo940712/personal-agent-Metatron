# Metatron 能力工具目錄

本文件是「使用者可見功能由哪個 capability、agent、interface、permission、storage
負責」的權威矩陣。程式面的同源資料在 `core/tools/catalog.py`。

## 邊界

- `core/tools/` 是應用能力層，讓 Discord、CLI、未來 MCP 共用；不是動態 plugin
  framework，也不是把所有 Python 函式公開。
- `core/stm.py`、SQL helper、writer dispatch 是內部實作，不是 capability API。
- `propose` 只建立並驗證 proposal／pending；真正落地仍只能經 deterministic
  writer boundary。這不要求 orchestrator 逐筆代轉。
- `AUTO_APPLY` 只涵蓋架構明定免確認的操作（目前是 `done`），仍經 writer 驗證。
- Agent allowlist 與 interface exposure 是兩個不同欄位；能力存在不代表所有 agent
  或 interface 都可呼叫。
- 「Agent allowlist」欄記錄的是**哪個子 agent 產生／擁有該 proposal**（例如 schedule
  agent 輸出 `schedule_change`），不代表該 agent 自己持有可呼叫的工具。schedule／
  curator／coding_tracker 是無工具的純函數 agent；目前只有 recall 有 internal
  read-only tool whitelist（見文末）。
- Agent 能呼叫 capability 與 agent 能改 shared state 也是兩個不同判斷。LLM 不會
  取得 raw SQL、DB connection、任意檔案寫入或裸 `writer.apply`。
- 排程 jobs 與 `skills/` 是獨立、可重跑的 CLI 管線，只登錄於 catalog，不搬入
  `core/tools/`。

## Permission

| 值 | 意義 |
|---|---|
| `read` | 唯讀能力，不改變 SoR |
| `propose` | 只產生／驗證 proposal，需確認時寫入 pending |
| `auto_apply` | 免確認，但仍走 writer 驗證 |
| `apply` | 驗證後落地；全系統只有 deterministic writer commit boundary，internal only |
| `job` | 獨立 CLI／scheduler 管線，不是互動 agent tool |

## 權威配對矩陣

空白 agent 表示確定性程式能力，不由子 agent 自主呼叫。

| Feature | Capability | Agent allowlist | Interface exposure | Permission | Storage / source | Implementation |
|---|---|---|---|---|---|---|
| 今日行程與待辦 | `schedule.today` | — | Discord, MCP | `read` | DB1 | `core.tools.schedule.today` |
| 本週行程 | `schedule.week` | — | Discord, MCP | `read` | DB1 | `core.tools.schedule.week` |
| 自然語言行程提案 | `schedule.propose` | `schedule` | CLI, Discord, MCP | `propose` | DB1 pending → writer | `core.tools.schedule.propose` |
| 新增待辦提案 | `tasks.propose` | `schedule` | CLI, Discord, MCP | `propose` | DB1 pending → writer | `core.tools.tasks.add` |
| 完成行程或待辦 | `tasks.complete` | — | Discord, MCP | `auto_apply` | DB1 via writer；跨表撞號需明確指定 kind | `core.tools.tasks.complete` |
| 專案進度 | `projects.status` | — | Discord, Dashboard, MCP | `read` | DB1 | `core.tools.projects.status` |
| 知識庫問答 | `memory.recall` | `recall` | CLI, MCP | `read` | vault, index, cold transcript | `core.tools.memory.query` |
| 記憶回水 | `memory.rehydrate` | `recall` | CLI, MCP | `read` | vault, cold transcript | `core.tools.memory.rehydrate` |
| 驗證後唯一 commit boundary | `writer.apply` | —（不直接給 LLM） | internal only | `apply` | DB1, vault | `core.writer.apply` |
| 提醒排程 | `job.remind` | — | CLI, scheduler | `job` | DB1 | `python -m core.agent --job remind` |
| 記憶蒸餾 | `job.consolidate` | `consolidator` | CLI, scheduler | `job` | DB1, vault, cold transcript | `python -m core.agent --job consolidate` |
| 專案追蹤 | `job.track` | `coding_tracker` | CLI, scheduler | `job` | DB1, git, Beacon, OpenCode | `python -m core.agent --job track` |
| 知識整理 | `job.curate` | `curator` | CLI, scheduler | `job` | vault | `python -m core.agent --job curate` |
| 主動建議 | `job.advise` | `advisor` | CLI, scheduler | `job` | DB1 advices, Discord | `python -m core.agent --job advise` |
| 知識偵察 | `job.scout` | `scout` | CLI, scheduler | `job` | DB1 watchlist, vault inbox | `python -m core.agent --job scout` |
| 個人模型 facets | `facets.list` | — | CLI | `read` | DB1 profile_facets | `python -m core.stm facets list` |
| 情境演練 | `scenario.rehearse` | `scenario` | CLI | `read`(非權威產物) | vault/scenarios（subprocess 隔離） | `python -m core.scenario rehearse <template>` |
| Threads 同步 | `skill.threads_sync` | — | CLI, scheduler | `job` | vault, skill data | `skills.runner:threads_sync` |

## 兩種 tool 名詞

1. **Capability tools（本文件）**：介面共用的使用者能力邊界。
2. **Agent internal tools**：例如 recall 迭代時可用的 `search`、`read_note`、
   `rehydrate` 唯讀白名單，定義於 `agents/recall.md` 與 `core/recall.py`。

兩者不能混為「所有函式皆可讓 LLM 呼叫」。MCP(part-006 已實作)只包裝 catalog
明確暴露的 capability——`core/mcp/tools.py` 十個工具:`schedule_list`/
`schedule_add`/`task_list`/`task_add`/`confirm`/`project_status`/`dev_status`/
`session_tail`/`directive_list`/`directive_push`,經 stdio(`channels/mcp_stdio.py`)
與 Tailscale HTTP(`channels/mcp_http.py`,bind guard fail-closed)兩種傳輸暴露;
寫入類工具回 pending 預覽,`confirm` 走 `pending_claim` 原子認領。agent internal
allowlist 仍由程式碼硬控。

## Control plane 與 data plane

- Metatron/orchestrator：路由、派工、跨 agent 衝突與最終整合。
- Capability gateway：依 agent/interface allowlist、scope、budget、timeout 執行工具。
- Writer：對 shared-state mutation 做 validator、確認閘門與 commit。

因此子 agent 可直接呼叫被授權的 `read`／`propose`／`auto_apply` capability，無需
讓 orchestrator 代辦每次 tool call；但 `auto_apply` 仍經 writer，且 confirm-required
操作仍 preview→confirm→commit。未來若新增 agent tool，必須同時指定 scope、最大
呼叫量及 allowed proposal types。
