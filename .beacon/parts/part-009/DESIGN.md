# part-009 DESIGN — Proactive Advisor / Subconscious(主動建議)

## Goal

讓 Metatron「活起來」——不是永遠在背景自我思考、也不是自主改你的狀態,而是**定期
醒來、看最近世界變了什麼、根據對你的了解產生可過期的建議、主動通知你,真實行動
仍由你確認**。這是「活」的正確定義,不是失控的自主 agent。

概念借鑑 OpenHuman `subconscious`(clean-room,見 backlog-027):cron 驅動、
world-diff、quiet-tick 不呼叫 LLM、失敗不推進 baseline、副作用仍走確認。

## Non-goals

- 不做常駐無限自我思考(cron tick,不是永動)
- 不自主改行程/待辦/專案(只產 advice,action 走 preview→confirm→writer)
- 不在無變化時燒 LLM(quiet tick 短路)
- 不做通用 planning agent(只針對你的實際 world-diff)
- 建議不堆積成另一種肥大 session(有過期、有配額、有去重)

## Chosen Design

### tick 流程(cron 觸發,借鑑 subconscious 通用 tick)

```
observe world-diff(自 baseline checkpoint 起的變化)
  → 無重要變化 → 直接 commit(刷新 baseline),不呼叫 LLM(quiet tick)
  → 有變化 → prepare context(唯讀讀相關 facets/events/schedule)
           → reflect(LLM:根據 Personal Model 產建議)
           → 產出 advice 提案(過欄位級驗證)
           → 主動推 Discord
           → commit(刷新 baseline)
  → reflect 失敗 → 不推進 baseline(下次重看同視窗)
```

### world-diff:最近變了什麼

每次 tick 只讀「自上次 baseline 後」的差異,不重掃全部:

```
- 新增/異動了哪些行程
- 哪些任務逾期
- 哪些專案停滯(coding_tracker 訊號)
- 作息是否偏離平常(part-007 routine facet)
- 新收了哪些知識(part-008)
- 哪些 goal 正在失速(part-007 goal facet)
```

無重要變化 → quiet tick,零 LLM 成本。

### advice 提案(只建議,不行動)

```jsonc
{
  "type": "advice",
  "priority": "low|medium|high",
  "observation": "你最近三天都在凌晨兩點後工作",
  "suggestion": "明天上午別排高認知負荷任務",
  "evidence_ids": ["evt:123", "evt:131"],   // 溯源,可回水
  "expires_at": 1752604800,                  // 過期即作廢,不堆積
  "actions": [                               // 可選:一鍵動作
    { "label": "建立 10:00 後再工作的提醒",
      "proposal": { /* 標準 schedule proposal */ } }
  ]
}
```

- advice 存 DB1 新表 `advices`(或復用 events + kind);推 Discord
- 按下 action → 對應的 proposal 走 **preview → confirm → writer**(不因是 advice
  而繞過確認)
- advice 本身不改任何真實狀態

### 防疲勞(建議不變噪音)

| 機制 | 內容 |
|---|---|
| 每日配額 | advice 每日上限(config) |
| 去重 | 同 observation 短期不重推 |
| 靜默期 | 使用者忽略某類建議 → 降頻(回饋進 part-007 facet 校準) |
| 過期 | expires_at 到 → 自動作廢 |
| 優先級 | 只主動推 medium/high;low 只在儀表板/查詢時顯示 |

### 校準回饋閉環

使用者接受/忽略/否決建議 → 回饋成 part-007 的 preference facet 證據 → 越用越準。

## Verification Targets

- world-diff 無重要變化 → quiet tick,不呼叫 LLM(mock LLM 斷言零呼叫)
- 有變化 → 產 advice 帶 observation/suggestion/evidence_ids/expires_at
- advice 的 action 落地走 confirm(未確認不落地)
- reflect 失敗 → baseline 不推進(下次重看)
- 每日配額/去重/過期生效;忽略某類 → 降頻

## Unit Test Strategy

pytest;LLM reflect mock;world-diff 是確定性讀取(測真);quiet-tick 短路、
baseline 推進/不推進、配額/去重/過期測真;advice→action→confirm 走既有 writer 路徑。

## Manual QA Strategy

塞幾天真實 events(含異常作息)→ 跑 advisor tick → Discord 收到合理建議 →
按 action → 確認 → 落地;無變化的日子跑 tick → 確認 quiet(無推播、無 LLM 成本)。

## Risks

- **建議品質**:保守優先級 + 校準回饋;低價值不推
- **疲勞**:配額/去重/靜默期/過期四重防護
- **成本**:quiet tick 短路;有變化才呼叫 LLM
- **越權**:advice 永不自己行動;action 一律 confirm

## Open Questions

- tick 頻率:每日一次(晨間 briefing)vs 多次——傾向每日晨間 + 重大變化即時,
  slice 定
- advice 存表 vs 復用 events kind:傾向獨立 `advices` 表(有 expires_at/priority
  語意)——slice 定
