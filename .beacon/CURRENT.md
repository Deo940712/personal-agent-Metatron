# CURRENT

Status: planning-only

part-005 完成(Phase 5 gate 真三源通過)。part-003.5 已設計(DESIGN + TODO 就位)。

## 已定執行順序(2026-07-13 使用者定案:兩個都做)

1. **part-006 slice-1**(先):stdio MCP + directives 第八表——它改共用檔 stm.py,
   先動 schema
2. **part-003.5**(後):唯讀儀表板——純新檔零重疊,且可順帶顯示 directives 版塊

## 待使用者動作(累積四批真 QA,不 block)

1. `MY_AGENT_LLM_API_KEY` → 真 LLM/embedding QA
2. Discord token + user id → 真 Discord QA
3. threads-sync Playwright session → 真同步 QA

## 下一步

promote part-006-slice-001 到本檔即開工。
