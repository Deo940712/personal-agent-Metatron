# part-002 DESIGN

## Goal

無狀態 Orchestrator core:`agent.py`(讀 STM → 派工子 agent → 綜合 → 寫回 → 死)、
`writer.py`(唯一寫入口:提案驗證 + 危險閘門)、LLM 薄層、schedule 子 agent 契約。
完成後:`python -m core.agent "明天14:00跟XX開會提前30分提醒"` → 預覽 → 確認 → DB1 有列。

## Non-goals

- curator / librarian / coding_tracker / recall 子 agent(part-003+ 才有資料可用)
- consolidation / 冷儲存 / 向量索引(part-003)
- Discord bot(part-002.5;本 part 的確認流走 CLI stdin)
- vault 寫入(schedule 提案只碰 DB1)

## Assumptions

- LLM = OpenAI 相容 API(backlog-002 定案):`openai` 套件 + base_url 環境變數
- 子 agent 執行 = 自寫薄層(backlog-006 定案):單次 chat.completions,無框架
- 模型分級:schedule 解析用 LLM_MODEL_CHEAP;orchestrator 意圖路由用 LLM_MODEL_STRONG
  (個人量級下路由也可先用 cheap,實測再調)
- Windows 子行程需 PYTHONUTF8=1(part-001 教訓)

## Design Options

1. **意圖路由用 LLM**(自然語言 → 判斷派給哪個子 agent)— 彈性,但每次呼叫多一跳
2. 意圖路由用關鍵字規則 — 便宜,但脆弱
3. **混合(選定)**:CLI 明確動詞(`--job remind` 等)直接走確定性路徑;
   自然語言輸入才用 LLM 路由(目前只有 schedule 一個目的地,路由極簡)

## Chosen Design

### 模組

| 檔案 | 職責 |
|---|---|
| `core/llm.py` | LLM 薄層:`complete(system, user, model, json_schema?) -> str\|dict`;openai 套件、base_url/key 從環境變數;錯誤重試 1 次;**呼叫記錄寫 events(actor=llm, 不含全文)** |
| `core/proposals.py` | 提案信封 dataclass + 各 proposal_type 的 payload 驗證(純 Python,無 LLM) |
| `core/writer.py` | `apply(proposal, confirm_fn) -> Applied\|Rejected\|NeedsConfirm`:§3.1 七條驗證 + §3.2 危險閘門;落地 schedule/tasks 寫入 + INSERT events |
| `core/subagents.py` | 子 agent 執行器:讀 `agents/<name>.md` → 組 prompt → llm.complete → 解析 JSON 提案(壞 JSON 重試 1 次,再壞 = 拒絕) |
| `agents/schedule.md` | schedule 子 agent 契約:系統 prompt + 輸出 JSON schema + few-shot |
| `core/agent.py` | Orchestrator 入口:INSERT agent_runs → 組上下文(stm.query)→ 路由 → 派工 → writer → UPDATE agent_runs → 回覆。`--job remind` = §6.6 確定性提醒(不經 LLM) |

### 確認流(CLI 版)

writer 遇到需確認的提案 → 印預覽 → `confirm? [y/N]`(stdin)→ y 落地 / 其他拒絕。
`confirm_fn: Callable[[str], bool]` 注入——part-002.5 的 Discord 按鈕替換同一介面。
非互動環境(scheduler trigger)遇需確認 → 一律拒絕(fail-closed)。

### schedule 子 agent I/O

輸入:使用者原句 + `now`(epoch)+ 現有 active 行程清單(供衝突檢查)。
輸出:`schedule_change` 提案 JSON(§3.1)。LLM 只解析,不寫 DB;
rrule 由 LLM 產字串、writer 用確定性程式驗證合法性。

## Verification Targets

- 單元:writer 七條驗證各一測(通過/攔截);閘門三層;proposals 解析
- 整合(mock LLM):`agent.py` 全流程——輸入句 → 提案 → 確認 → DB1 有列 → events 有記錄
- 整合(真 LLM,手動):一句中文排程 → 預覽正確 → y → `stm schedule list` 可見
- 無狀態:連續兩次獨立呼叫,第二次讀得到第一次的結果(僅經 DB1)
- `--job remind`:到期行程觸發 console 通知 + reminded_at 更新;rrule 前推

## Unit Test Strategy

pytest;LLM 一律 mock(注入 fake complete_fn),真 LLM 只在手動 QA。
writer 測試不 mock sqlite。confirm_fn 注入 lambda 控制 y/N 路徑。

## Manual QA Strategy

設好環境變數後:`python -m core.agent "明天下午兩點開會 提前30分提醒"` →
檢查預覽的時間解析正確 → y → list 確認;再跑 `--job remind`(把 remind_at 改到過去)看 console 通知。

## Risks

- LLM 回傳 JSON 不穩 → schema 約束 + 重試 1 次 + 壞 JSON 即拒絕(不猜)
- 時區:LLM 解析「明天下午兩點」需知道現在本地時間 → prompt 注入 now + 時區
- OpenAI 相容端點差異(有些不支援 response_format)→ llm.py 降級為 prompt 內嵌 schema + 自行 parse

## Open Questions

(無——兩個 blocker 已隨 backlog-002/006 定案)
