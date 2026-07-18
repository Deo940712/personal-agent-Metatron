# part-010 DESIGN — crowd-scenario integration(情境演練)

## Goal

讓 Metatron 能「演練未來」——用你自己的 crowd-scenario 引擎,把一個已決定的情境
交給一群合成 persona 演練,產出**非權威的敘事報告**,幫你在做決定前先看幾種可能
反應。用於個人排程壓力、專案取捨、習慣改變等「如果…會怎樣」的探索。

crowd-scenario 是你自己的 repo(MIT、零 runtime 依賴、確定性、firewall 隔離),
天生契合本專案「Agent 提議、程式驗證」哲學。決定:**vendored 釘版 + subprocess CLI
呼叫**(第二個 vendored 黑箱,同 threads-sync)。

## Non-goals

- 不把 crowd-scenario 當事實預測器(輸出硬標 non-authoritative)
- 不讓它讀寫 DB1/vault/transcript 原文(只吃 bucket seed、只回報告)
- 不餵原始數字給它(firewall:只吃 ordinal bucket)
- 不改 crowd-scenario 原始碼(vendored 黑箱,釘 commit,零修改)
- 不做大型多人社會模擬(那是 MiroFish 的 part-011 領域)

## Chosen Design

### 整合方式:vendored + subprocess(使用者定案 2026-07-14)

```
skills/crowd_scenario_vendor/   ← vendored clone(pin commit;VENDORED.md;零修改)
core/scenario.py                ← 薄 adapter:Metatron 資料 → bucket seed →
                                   subprocess 呼叫 crowdscenario CLI → 解析報告
```

- 同 threads-sync:pin 一個 commit,記在 VENDORED.md,當黑箱用
- subprocess 隔離:crowd-scenario 崩潰/漂移不影響 core
- 它本來就無 runtime 依賴、確定性——subprocess `python -m crowdscenario run` 即可

### 資料流(單向、firewall 化)

```
Metatron 狀態(schedule/tasks/facts/facts)
  → 降識別 + bucket 化(raw 數字 → ordinal bucket)
     例:sleep 4.7h → "severely_low";tasks 19 → "overloaded"
  → 組 ScenarioSeed(crowd-scenario 契約:只吃 ordinal,拒 raw number)
  → subprocess:python -m crowdscenario run --domain <pack>
  → CrowdNarrative(non_authoritative=true, synthetic_population=true)
  → 存 vault/scenarios/(專區,不進 semantic 事實層)
  → 標「模擬演練 / 非事實 / 非預測」
```

crowd-scenario 的 firewall(contracts.py)本來就硬性拒絕 raw number 進 seed、
輸出硬標 non_authoritative——Metatron 這端只要負責 bucket 化與標記存放。

### 個人 domain packs(新增)

crowd-scenario 已有 stock_tw / product / software packs。為個人助理新增:

| pack | 用途 |
|---|---|
| `personal_schedule` | 排程壓力演練(如果明天同時處理 A/B/C) |
| `habit_change` | 習慣改變的多種自我反應(如果早睡一週) |
| `project_portfolio` | 專案取捨(如果 side project 延後一週) |

packs 是 crowd-scenario 的 DomainPack 協定(persona archetypes + axes),寫在
vendored 之外的本地擴充或 upstream 貢獻——slice 設計時定放哪。

### 輸出定位(絕不當事實)

- 存 `vault/scenarios/`,不進 semantic/(不污染事實層)
- frontmatter 標 `source: scenario_rehearsal` + `non_authoritative: true`
- recall 回答時若引用到 scenario,必須標「這是模擬演練,非事實/非預測」
- 不進 Personal Model facet 證據(演練不是你的真實偏好)

## Verification Targets

- Metatron 資料 → bucket seed:raw 數字被 bucket 化,seed 不含原始數字
- subprocess 呼叫成功解析 CrowdNarrative;crowd-scenario 崩潰 → core 不受影響
- 輸出存 vault/scenarios/ 標 non_authoritative;不進 semantic/
- 個人 domain pack 產出合理 persona 反應鏈
- recall 引用 scenario → 帶「模擬/非事實」標記

## Unit Test Strategy

pytest;subprocess mock(不跑真 vendored,測 adapter 的 bucket 化與解析);
bucket 化邏輯測真(raw → ordinal);non_authoritative 標記與存放路徑測真。
真 crowd-scenario subprocess 是手動 QA(vendored 就位後)。

## Manual QA Strategy

vendored crowd-scenario 就位 → 用真實 schedule/facts 產 personal_schedule 演練 →
subprocess 跑通 → 報告存 vault/scenarios/ 標記正確 → recall 引用帶模擬標記。

## Risks

- **誤當事實**:硬標 non_authoritative + 專區存放 + recall 標記 + 不進 facet
- **vendored 漂移**:pin commit + VENDORED.md(同 threads-sync 慣例)
- **subprocess 成本/失敗**:隔離,壞掉不影響 core;確定性、無網路
- **firewall 繞過**:crowd-scenario 契約自帶 raw-number 拒絕;Metatron 這端也 bucket 化

## Open Questions

- 個人 domain packs 放 vendored 外本地擴充 vs upstream 貢獻回 crowd-scenario:
  傾向本地擴充(快、不動 vendored),好的再 PR upstream——slice 定
- 演練觸發:純使用者要求 vs part-009 advisor 也可觸發——傾向先純使用者要求,
  advisor 觸發列後續——slice 定
