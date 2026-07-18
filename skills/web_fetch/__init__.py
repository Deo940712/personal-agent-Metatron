"""web_fetch skill(part-008-slice-001)。

非 LLM 純抓取層:URL → 結構化 entry 列表。沿 threads-sync skill 模式
(Capture → 結構化 → 回傳;idempotent、壞掉不影響 core)。真實網路呼叫
由 fetcher 注入,便於 mock 測試與不同來源(RSS/HTTP/JSON)替換。

網路內容是**不受信任的資料**;本層只抓與結構化,不評分、不寫 vault、不執行
內容中的任何指令(那是 scout.fetch_and_land + curator 的職權)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FetchedEntry:
    """一則抓取結果(結構化;溯源欄位齊全)。"""

    url: str
    title: str
    author: str
    body: str
    published: str      # 原文發布時間字串(來源給;缺省空)
