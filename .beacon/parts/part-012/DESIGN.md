# part-012 DESIGN — 對話式 orchestrator（LLM-first 路由，backlog-033）

## Goal

讓 Metatron「聰明且人性化」——使用者真機使用後的第一個體感回饋。任何訊息先由
LLM 理解意圖，分派給既有能力，用自然語言回覆；聽不懂就友善追問，而不是
「這不是行程/待辦」。**寫入鐵律完全不變**（提案→writer→確認）；變的只是
理解與表達層。

## Non-goals

- 不改寫入紀律（所有 mutation 仍走 preview→confirm→writer）
- 不做多輪對話狀態（核心仍無狀態；「追問」是單則回覆引導，不是 session 記憶）
- 不做通用 chatbot / 人格扮演（閒聊給一句自然回應 + 能力提示即可）
- 不移除確定性快徑（today/done N 等精確指令仍零 LLM 直達——省錢且快）
- 不讓 LLM 自組 SQL/檔案操作（意圖分類輸出是 enum，不是自由代碼）

## 根因（backlog-033，真機 QA 實證）

1. `chat.handle_message` 是關鍵字表：未命中全部丟給**單一用途**的排程解析
   →「明天」得到「這不是行程/待辦」
2. recall 在 Discord 被 `_KNOWLEDGE_PREFIXES` + `allow_recall=False` 擋死
   （§4.1 內容分級——當時無加密通道；現在有內網反代/Tailscale，決策過時）
3. LLM 只解析排程，沒有「意圖分類 → 能力選擇 → 自然回覆」層

## Chosen Design

### 分層：快徑保留，慢徑升級

```
訊息進來
  ├─ 確定性快徑(零 LLM,不變):today/今天、week/本週、proj/專案、
  │   done N、todo X、查/recall 前綴 → 直達既有能力
  └─ 其餘 → LLM 意圖路由(router 子 agent,單次 cheap 呼叫)
        → {"intent": enum, "argument": str, "reply_style": str}
        intent ∈ schedule_write   排程/待辦意圖 → schedule_tools.propose(現行為)
                 schedule_query   查行程(含「明天」「下週三有什麼」)→ 確定性讀 DB 回答
                 knowledge        知識問答 → recall(Discord 也開放)
                 advice           「有什麼建議」→ 讀 pending advices
                 status           「最近如何/專案狀況」→ projects + advices 摘要
                 smalltalk        閒聊/問候 → 自然一句 + 能力提示
                 unclear          聽不懂 → 友善追問(帶猜測:「你是想排行程還是查資料?」)
```

### 新元件

- `agents/router.md`：意圖分類契約（cheap model、單次呼叫、輸出 JSON enum；
  few-shot 含「明天」「我存過哪些 RAG」「最近怎樣」「哈囉」）
- `core/router.py`：`classify(text, _api) -> Route`；欄位級驗證（intent 必在
  enum、argument 是 str）；LLM 失敗/非法輸出 → fallback 現行 schedule 路徑
  （**降級不斷服務**）
- `schedule_query` 確定性讀取器：解析「明天/後天/下週N/日期」時間窗（LLM 給
  normalized date range，程式驗證後查 DB）——LLM 理解語言，程式算時間與查詢
- Discord 開 recall：`allow_recall` 預設 True（內容分級決策標記過時，記入
  INTERFACES/MEMORY 文件）

### 回覆風格

能力結果 → 短自然語（不改資料，只改措辭）：查詢結果前加一句人話
（「明天有 2 件事：」）；unclear 給具體猜測而非使用說明書。不用第二次 LLM
呼叫做「潤稿」——模板 + router 給的 reply_style 就夠（省錢）。

### 成本控制

- 快徑（精確指令）零 LLM——高頻操作不變貴
- router 用 cheap model、輸出 JSON 極短
- 一則訊息最多 2 次 LLM（router + 能力本身若需要,如 schedule 解析/recall）

## Verification Targets

- 「明天」→ 列明天行程（不再是「這不是行程/待辦」）
- 「我存過哪些 RAG 做法」在 Discord → recall 帶引用回答
- 「最近有什麼建議」→ 列 pending advices
- 「哈囉」→ 自然回應 + 能力提示；亂碼/不明 → 友善追問
- 快徑不變：today/done N 零 LLM 直達（mock 斷言零呼叫）
- router LLM 失敗 → fallback 排程解析，服務不中斷
- 寫入仍走確認：schedule_write 意圖照舊 preview→confirm

## Unit Test Strategy

pytest；router LLM mock（各 intent 的分類重放 + 非法輸出 fallback）；
schedule_query 時間窗解析測真（確定性部分）；Discord/CLI 走 application.invoke
整合測；快徑零 LLM 斷言。

## Manual QA Strategy

Discord 真機：打「明天」「我存過哪些 X」「最近怎樣」「哈囉」「亂打一串」，
逐一驗證回覆自然且正確；再打「明天下午兩點開會」確認寫入流程不變。

## Risks

- **成本**：每則非快徑訊息 +1 次 cheap LLM 呼叫——個人量級可接受；快徑保留
- **誤分類**：寫入意圖誤判成查詢 = 少做事（安全方向）；查詢誤判成寫入仍有
  preview→confirm 攔截——**錯誤都落在安全側**
- **router 失敗**：fallback 現行路徑，行為退回今天的水準，不會更糟

## Open Questions

- schedule_query 的時間窗解析：LLM 給 ISO date range + 程式驗證 vs 純程式解析
  「明天/下週」詞彙表——slice 設計時定（傾向 LLM 給、程式驗，覆蓋面大）
- smalltalk 是否帶入 facets 個人化（「早安,今天你有 3 件事」）——slice-002 定
