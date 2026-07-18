# part-007 DESIGN — Personal Model(個人模型)

## Goal

讓 Metatron 逐步熟悉你的偏好、作息、流程與方法——但不靠長 session、不靠把聊天
紀錄塞回 prompt。改用**證據驅動的 stability facets**:每個關於你的事實帶證據、
信心、穩定度與生命週期,一次行為不會變成永久人格,重複出現才升級為穩定偏好。

概念借鑑 OpenHuman `learning` 子系統(clean-room:讀架構、用 Python 自寫,不搬
GPL 程式碼,見 backlog-027)。落地遵守本專案鐵律:facets 是 DB1 結構化資料、
vault/agent/profile 只是可讀投影、寫入走同機制驗證、使用者手動永遠優先。

## Non-goals

- 不做長 session / 對話歷史累積(核心無狀態不變)
- 不做把所有聊天紀錄當記憶(只抽穩定信號)
- 不自動改行程/待辦(Personal Model 只產知識,行動仍走 schedule + 確認)
- 不做人格模擬 / 情緒狀態機(那是玩具,不是助理)
- facets 不繞過 writer / 不物理刪除(forgotten = 停用,不刪原證據)

## Chosen Design

### DB1 新表:profile_facets(免疫衰減,同 events 的 immune 類)

```sql
CREATE TABLE profile_facets (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  facet_class    TEXT    NOT NULL,   -- preference|identity|routine|workflow|veto|goal|tooling|style
  facet_key      TEXT    NOT NULL,   -- 類內唯一鍵,如 'work_hours' / 'editor' / 'reply_lang'
  value          TEXT    NOT NULL,   -- 目前值(文字;結構化走 JSON)
  confidence     REAL    NOT NULL DEFAULT 0.0,   -- 0.0-1.0
  stability      REAL    NOT NULL DEFAULT 0.0,   -- 遞增穩定度(重複證據累積)
  evidence_count INTEGER NOT NULL DEFAULT 0,
  evidence_ids   TEXT,               -- JSON array:冷儲存 entry_id(溯源,可回水)
  state          TEXT    NOT NULL DEFAULT 'provisional'
                 CHECK (state IN ('provisional','stable','superseded','forgotten')),
  user_state     TEXT    NOT NULL DEFAULT 'auto'
                 CHECK (user_state IN ('auto','pinned','forgotten')),   -- 使用者硬覆蓋
  superseded_by  INTEGER,            -- 指向新 facet(矛盾修正,不刪舊)
  first_seen_at  INTEGER NOT NULL,
  last_seen_at   INTEGER NOT NULL,
  created_at     INTEGER NOT NULL
);
-- 「同 class+key 只一個 active」用 partial unique index 實作(slice-000 修正:
-- 原設計 UNIQUE(class,key,state) 會讓同 key 第二次 supersede 撞約束——
-- 兩筆 superseded 同 key 是合法歷史,唯一性只該限制 active 列)
CREATE UNIQUE INDEX idx_facets_unique_active
  ON profile_facets(facet_class, facet_key)
  WHERE state IN ('provisional','stable');
CREATE INDEX idx_facets_active ON profile_facets(facet_class, state)
  WHERE state IN ('provisional','stable');
```

### 生命週期(狀態機)

```
observed(單次證據,不建 facet,只累積)
  → provisional(首次建 facet,stability 低)
  → stable(重複證據累積過閾值)
  → pinned(使用者顯式確認/pin → stability 無限、免動)
  → superseded(新值取代,舊 facet 留 superseded_by 不刪)
  → forgotten(使用者要求忘記 → 停用,不再載入,證據仍在)
```

- **pinned ⇒ 評分無效化**(使用者硬贏);**forgotten ⇒ 阻止再升級**
- 一次行為不能直接 stable;需 N 次證據(N 為 config 可調,初值保守)
- 矛盾偵測沿用 part-004.5 Mneme 概念:新值與既有 active facet 衝突 → 並列詢問
  或 supersede(過欄位級驗證),不靜默覆蓋

### 證據來源(確定性收集,不靠 LLM 猜)

| 來源 | 抽出什麼 facet |
|---|---|
| schedule/task 實際完成時間 | routine(工作時段、休息模式) |
| 使用者在 CLI/Discord 的顯式修正 | preference / veto |
| 接受或忽略哪些建議(part-009 回饋) | preference 校準 |
| consolidation 蒸餾出的偏好類事實(現有 agent/profile) | preference / identity |
| 顯式「存成 SOP」 | workflow(程序記憶) |

抽取器是確定性 producer + 一個保守的 LLM 分類(過欄位級驗證);升級由
stability detector(純函數,可重放測試)決定。

### vault 投影(人可讀 + recall 可見)

`profile_facets` 的 active 列投影成 `vault/agent/profile/` 筆記(現有 §4.2 結構),
`source: agent_knowledge` + `source_ids` 溯源。投影是衍生物:facets 是真相,壞了
可重投影。這讓「我的偏好是什麼」用 recall 也查得到——不是黑盒。

### 寫入路徑

facet 的建立/升級/supersede 都走 writer(新增 `profile_facet` proposal type +
`writer.apply_facet`),過欄位級驗證(class/state 合法、evidence_ids 屬實、
不覆蓋 pinned/forgotten)。使用者手動編輯 vault/agent/profile 永遠優先(manual_tags)。

## Verification Targets

- 單次證據不建 stable facet;N 次同證據 → provisional → stable(stability detector 純函數測)
- pin 後評分不再改動;forget 後不再升級、不再載入,但證據列仍在
- 矛盾新值 → supersede 舊 facet(舊留 superseded_by,不刪)
- active facets 投影成 vault 筆記且 recall 查得到
- writer 攔截:偽造 evidence_ids / 覆蓋 pinned → 拒絕

## Unit Test Strategy

pytest;stability detector 與 supersede 決策是純函數(mock 證據流,可重放);
writer facet 驗證測真(不 mock DB);LLM 分類 mock。

## Manual QA Strategy

連續幾天真實使用後:`python -m core.stm facets list` 應出現合理 provisional/stable
facets;pin 一個、forget 一個,重跑確認狀態正確;Obsidian 開 vault/agent/profile
看投影。

## Risks

- **過度學習/誤學**:保守閾值 + 使用者可 forget;低信心不投影
- **facet 爆量**:per-class 配額(同 curator 分類配額);低 stability 久不命中衰減
- **隱私**:facets 是本機 DB1,不外流;不抓帳號私料(那是 part-008 的 allowlist 管)

## Open Questions

- stability 公式與升級閾值:初值保守,真實使用 1-2 月有數據再調(同 backlog-026)
- routine 抽取要不要獨立 job vs 掛在 consolidate:傾向掛 consolidate(夜間已在跑)
  ——slice 設計時定
