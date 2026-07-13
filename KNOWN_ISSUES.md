# KNOWN ISSUES — 反查稽核報告

> 建立:2026-07-13(part-002-slice-002 完成後、slice-003 開工前的反查)
> 方法:通讀五個模組 + **探針腳本實證**(每個問題都有實際重現,不是猜測)。
> 狀態欄:`open` = 未修;`fix@NNN` = 排定在該 slice 修;`accepted` = 已知並接受。

## 嚴重度 HIGH(會 crash 或資料毒化,slice-003 開工前必修)

### B1 `fixed@002-3` update 空 fields → SQL 語法錯誤 crash

- **重現**:`{"action":"update","fields":{}}` → `OperationalError: near "WHERE": syntax error`
- **根因**:`writer._apply_change` 組 `UPDATE ... SET ` 時 fields 為空,SET 子句空字串
- **影響**:LLM 完全可能產出空 update;writer 該拒絕卻 crash(未捕捉例外 → orchestrator 崩潰、agent_runs 卡 running)
- **修法**:`proposals._validate_change`:update 時 `fields` 為空 → ProposalError

### B2 `fixed@002-3` update 可把 NOT NULL 欄位設成 None → IntegrityError crash

- **重現**:`{"action":"update","fields":{"title":null}}` 或 `{"start_at":null}` → `IntegrityError: NOT NULL constraint failed`
- **根因**:validator 的 int 檢查刻意放行 None(`if fields[key] is not None`),但 title/start_at 是 NOT NULL
- **影響**:同 B1——crash 而非優雅拒絕
- **修法**:validator 區分 nullable(end_at/remind_at/rrule/detail/due_at 可 None=清除)與 NOT NULL(title/start_at 不可 None)

### B3 `fixed@002-3` 界外 epoch → 一筆壞資料讓所有 list 永久 crash(資料毒化)

- **重現**:`start_at=99999999999999`(或負數)→ 預覽/`fmt_when` → `OSError: [Errno 22]`
- **更嚴重**:此值一旦落庫(見 B4 路徑或直接 CRUD),**之後每次 `schedule list` 都 crash**——一筆壞資料癱瘓整個 CLI
- **根因**:validator 只查 `isinstance(int)`,不查範圍;`fmt_when` 直接 `fromtimestamp`
- **修法**(雙層):① validator 加 epoch 合理範圍(2000-01-01 ~ 2100-01-01:946684800‥4102444800);② `fmt_when` 防禦性 try/except 回傳 `?invalid`

### B4 `fixed@002-3` bool 通過 int 檢查

- **重現**:`start_at=true`(JSON boolean)→ `isinstance(True, int)` 為真 → 落庫為 1(=1970 年)
- **影響**:LLM 產出 JSON true/false 時寫入垃圾時間,靜默無錯
- **修法**:int 檢查改 `isinstance(v, int) and not isinstance(v, bool)`

## 嚴重度 MEDIUM(不 crash 但行為錯誤或有風險)

### B5 `fixed@002-3` CLI `parse_when` 壞輸入 → 裸 traceback

- **重現**:`python -m core.stm schedule add x --start not-a-date` → `ValueError: Invalid isoformat string` 全 traceback
- **修法**:CLI 層 try/except → 友善訊息 + exit 2

### B6 `mitigated@002-3` done/cancel 免確認 + prompt injection = 可無確認關閉任意列

- **重現**:confirm_fn=None(scheduler 情境)下 `{"action":"done","target":"4"}` 照樣 applied
- **分析**:「done 免確認」是規格(§3.1 規則 7),單獨看沒錯;但組合「LLM 解析不可信輸入」時,注入文字可讓 LLM 產 done/cancel 提案關掉任意行程
- **緩解**(slice-003 實作):orchestrator 只接受 done/cancel 的 target ∈ 本次注入的 active_items id 清單;不在清單 → 降級為需確認
- **殘餘風險**:接受(單人系統、行程可自行改回)

### B7 `partial@002-3` `db=None` 預設指向生產 DB——測試/新程式碼忘帶 db 就寫真資料

- **重現**:`llm.complete(...)`(不帶 db)→ `stm.event_append(None,...)` → 寫進 `config.STATE_DB`
- **分析**:CLI 情境是 feature,內部模組是 footgun。slice-002 測試都有帶 db 所以沒炸,但未來忘一次就污染生產 events
- **修法**:core 內部函式間傳遞 db 改為必填參數(CLI 入口才解析 None→config);至少在 llm.py/writer.py 內部呼叫鏈不允許隱式 None

### B8 `fixed@002-3` `llm.complete` 對不可重試錯誤也重試

- **重現**:401 無效 key / 404 模型不存在 → 仍重打第二次
- **影響**:浪費延遲與費用;錯誤訊息延後暴露
- **修法**:僅對 timeout/connection/5xx 重試;4xx 直接拋

### B9 `open→fix@002-5前` `_now_line` 時區偏移用 `time.daylight`(定義旗標)而非 `tm_isdst`(當前生效)

- **現況**:台灣無 DST,兩者皆 0,**目前正確**
- **風險**:遷 VPS 到有 DST 的時區(歐美)→ 偏移差 1 小時 → LLM 換算「明天下午兩點」全錯 1 小時
- **修法**:改用 `time.localtime().tm_isdst` 判斷;遷 VPS checklist(backlog-008)加一條

## 嚴重度 LOW(觀測性/衛生)

### B10 `open` `connect()`/`existing_tables()` 對不存在路徑會靜默建空檔

- sqlite 預設行為:connect 即建檔 → 打錯路徑得到 0 表空 DB 而非報錯
- **修法**:connect 加 `require_exists=True` 參數(init 除外);或 URI `mode=rw`

### B11 `fixed@002-3` `_reject` 把 desc 塞進 events.target——target 欄位語意被污染

- events.target 應是「影響對象 id/路徑」,拒絕記錄卻塞了提案描述字串
- **修法**:拒絕時 target 留 None 或帶真正的 p.target

### B12 `info` rrule 驗證接受冗餘組合(如 `FREQ=DAILY;BYDAY=MO`)

- 無害(BYDAY 被 DAILY 忽略),slice-003 前推實作時決定是否收緊

## 流程教訓(記入測試策略)

1. **邊界值測試缺席**:slice-001 的 21 個 writer 測試全是「合法值 vs 非法 enum」,
   沒測空集合、None、界外數值、bool——這正是 7 個 crash 全漏網的原因。
   → slice-003 起,每個 validator 必配 boundary 測試(空/None/界外/型別偽裝)。
2. **「一筆壞資料毒化所有讀取」是最危險模式**(B3):寫入驗證要比讀取顯示嚴,
   讀取顯示要比寫入驗證韌(雙層防禦,兩層都要有)。
3. 探針腳本已刪;重現命令都在本文件,修復時逐條轉成 regression test。


## 修復記錄(2026-07-13, part-002-slice-003)

- B1-B5, B8, B11:**fixed** — regression tests 在 tests/test_known_issues.py(逐條對應)
- B6:**mitigated** — agent.py `_enforce_target_whitelist`:done/cancel 只接受本次
  active 清單內的 id;越界拒絕並記 events(tests/test_agent.py::test_b6_*)
- B7:**partial** — llm/writer 呼叫鏈已全程顯式傳 db;完全移除 None 預設留待
  part-003(改動面大,屆時 ltm.py 一起規範)
- B9(DST):**open** — 已在 backlog-008 VPS 遷移 checklist;B10/B12:**open**(LOW)

## Audit gate 記錄(2026-07-13, part-003-slice-002)

探針 8 項,實證 3 個 crash/缺陷,全部已修 + regression tests:

- **S5 `fixed@003-2`** LLM 回 groups 非 list → AttributeError crash → 整批視為無效回應留 trash
- **S6 `fixed@003-2`** group 為字串混入 → AttributeError crash → _validate_group 第 0 條(必須是 object)
- **S8 `fixed@003-2`** write_note 打錯 subdir 靜默建野目錄 → ALLOWED_SUBDIRS 白名單
- probed clean: S1(YAML 特殊字元 roundtrip)、S2(summary 換行已在 write_note 清洗)、
  S3(body 含 --- 不切壞)、S4(同 event 被兩組引用 = 合法,archived 冪等)、
  S7(injection 面已知:listing 拼進 prompt 無跳脫,防線 = 欄位級驗證,注入只能影響內容不能繞驗證)

## Audit gate 記錄(2026-07-13, part-002.5-slice-001)

探針 5 項,發現 1 個 DESIGN 缺陷(照 continuous-loop:改 DESIGN 再進下一 slice):

- **A2'/A3' `design-fix@002.5-1`** 非同步確認第二階段(pending dict → 落地)缺重驗:
  precheck 到按鈕相隔數分鐘,target 可能被刪/改;且 pending.proposal 是 dict 而
  apply_validated 吃 Proposal 物件(型別不符會炸)。
  → 新增 `writer.confirm_and_apply(dict)`:接 dict、**重跑 precheck**、通過才落地。
  DESIGN.md 追加 slice-001 稽核發現表;3 個 regression tests。
- probed clean: A1(precheck 後 status 改仍可 update——合法)、A4(apply 非法 → rejected)、
  A5(同提案多 pending 無去重——chat 層保證一訊息一 pending,單人低頻可接受)

## Audit gate 記錄(2026-07-13, part-002.5-slice-002)

實作中即抓到:`todo`/`done` 無參數(尾隨空白被 strip)會落 LLM → 分派層接住。
探針 7 項,發現 1 個:

- **C7 `fixed@002.5-2`** 純空白訊息 → 落 LLM 白打 API → 分派層加空訊息守衛
- probed clean: C1(大小寫前綴一致)、C2(前綴當內容不誤判)、C3(負數 pending id 回失效)、
  C4(done 已落地行程 OK)、C5(「找時間開會」不被知識查詢誤攔)、C6(channel_ref 持久化)
- regression: test_c7/c1/c6 in test_chat.py

## Audit gate 記錄(2026-07-13, part-002.5-slice-003)

探針 6 項,發現 1 個一致性瑕疵(LOW):

- **D2 `fixed@002.5-3`** encode_custom_id(-5) 產出可解碼失敗的字串 → 編解碼不對稱。
  pending_id 是 AUTOINCREMENT 永遠正,顯式化:encode 拒絕 <1 的 id。
- probed clean: D1(超大 id 解析/冒號注入擋下/空字串)、D3(白名單去重)、
  D4(負數/16進位垃圾濾除)、D5(user 白名單邏輯)、**D6(模組載入不 eager import
  discord.py——薄 adapter 解耦成立)**

## Audit gate 記錄(2026-07-13, part-004-slice-002 curator)

手動 QA 端到端即稽核,抓到 1 個真缺陷當場修:

- **E1 `fixed@004-2`** dedupe 正本選擇依 path 字母序——誰是正本變成檔名運氣
  (rag_dup 排在 rag_tip 前就反了)→ 改依 frontmatter date(發布時間早者為正本);
  無 date 排最後。手動 QA 腳本驗證:正本入庫可檢索、轉發標 duplicate。
- 測試覆蓋依 KNOWN_ISSUES boundary 慣例:score 界外/bool 偽裝/詞彙表外 tag/
  空 tags/161 字 summary/evidence 不屬實/幻覺 path/LLM 失敗留 inbox/配額 defer,
  全部 19 tests 綠。

## Audit gate 記錄(2026-07-13, part-004-slice-003 recall)

探針 7 項,發現 1 個(當場修 + regression):

- **R2 `fixed@004-3`** answer 的 citations 為字串(非 list)→ 曾靜默轉空放行
  =「有主張無引用」繞過硬規則 → 改拒答(格式錯誤,原回答丟棄)
- probed clean: R1(非 dict move → LLMError 誠實回)、R3(超長 answer 截 500)、
  R4(超長 query 截 200)、R5(絕對路徑擋)、R7(int citation → 驗證失敗拒答)、
  R6(筆記 body 注入面已知:防線 = 引用驗證獨立於文字,假 id 必被抓)
