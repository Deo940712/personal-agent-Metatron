"""知識偵察 Scout(part-008;ARCHITECTURE §15.1)。

讓知識能主動從網路補充——但**網路內容是不受信任的資料,不是指令**。
slice-000 只做確定性基座:allowlist(fail-closed)、research query 建構、
watchlist 到期判定;不抓網路、不呼叫 LLM。

防 prompt injection 硬規則(DESIGN §防注入):allowlist 限定可信源、研究 query
過 allowlist、抓取內容不直接觸發寫入(必經 inbox → 評分),external_untrusted
標籤跟著內容(slice-001)。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import config
from core import stm

DAY = 86_400


def _normalize_domain(host: str) -> str:
    """小寫 + 去 port + 去前導 www.(allowlist 比對用)。"""
    host = host.lower().split(":", 1)[0].strip(".")
    return host[4:] if host.startswith("www.") else host


def is_allowed_url(url: str, allowlist: list[str] | None = None) -> bool:
    """網域 allowlist 檢查(fail-closed)。

    只准 http(s) + 網域(含子網域)在清單內。非法 scheme / 空 host / 不在清單
    → False。allowlist 空 = 全拒(必須顯式加信任來源)。
    """
    domains = config.SCOUT_ALLOWLIST_DOMAINS if allowlist is None else allowlist
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    host = _normalize_domain(parsed.hostname or "")
    if not host:
        return False
    for allowed in domains:
        allowed = _normalize_domain(allowed)
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def build_query(topic: str) -> str:
    """確定性 research query 建構(不呼叫 LLM;slice-000)。

    保守:只把 topic 正規化成查詢字串,不讓 LLM 自組任意 URL。實際搜尋端點
    的 query 語法在 fetcher(slice-001);此處只出穩定字串。
    """
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    return " ".join(topic.split())


def due_watchlist(db: Path | None, now_ts: int | None = None) -> list[dict]:
    """回到期需複查的 active watchlist 主題(低頻)。

    到期 = 從未查過,或距 last_checked_at 已超過 max(interval_days,
    SCOUT_MIN_INTERVAL_DAYS)天。來源 URL 不在 allowlist 的一律排除(fail-closed)。
    """
    now = now_ts if now_ts is not None else stm.now()
    out = []
    for w in stm.watchlist_list(db, state="active"):
        if not is_allowed_url(w["source_url"]):
            continue
        interval = max(w["interval_days"], config.SCOUT_MIN_INTERVAL_DAYS)
        last = w["last_checked_at"]
        if last is None or now - last >= interval * DAY:
            out.append(w)
    return out


# ── 抓取落地(part-008-slice-001)──────────────────────────────────────
# 網路內容 = 不受信任資料。抓取只落 inbox(帶溯源 + external_untrusted 標籤);
# **不直接觸發任何 writer 寫入**——必經 curator 評分 + writer 驗證(slice-002 job)。

def fetch_and_land(db: Path | None, vault: Path, source_url: str, topic: str,
                   fetcher, *, now_ts: int | None = None,
                   max_entries: int | None = None) -> dict:
    """抓一個來源 → 每則寫 inbox 筆記(external_untrusted + 來源溯源)。

    - allowlist 先驗(fail-closed):不在清單 → 拒絕、不抓、回 rejected。
    - fetcher(url) → list[FetchedEntry];抓取層容錯(壞來源回空)。
    - 每則落 vault/semantic inbox 筆記:frontmatter 帶 source='web'、url、author、
      captured_at、content_hash、date(published)、`external_untrusted: true`、
      tags=['inbox']。**不評分、不進 registry**——那是 curator(slice-002)。
    回統計 dict。
    """
    from datetime import datetime

    from core import curator_pre, ltm

    if not is_allowed_url(source_url):
        stm.event_append(db, "scout", "proposal_rejected",
                         f"fetch blocked: url not in allowlist: {source_url}")
        return {"landed": 0, "rejected": "not_allowed"}

    ltm.init_vault(vault)
    ts = now_ts if now_ts is not None else stm.now()
    captured = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    cap = max_entries if max_entries is not None else config.SCOUT_MAX_PER_RUN

    entries = fetcher(source_url)[:cap]
    landed = 0
    for entry in entries:
        # 逐則 URL 也要在 allowlist(link 可能跳出信任源)——fail-closed
        if entry.url and not is_allowed_url(entry.url):
            stm.event_append(db, "scout", "proposal_rejected",
                             f"entry url not in allowlist: {entry.url}")
            continue
        frontmatter = {
            "source": "web",
            "url": entry.url or source_url,
            "author": entry.author or "unknown",
            "date": entry.published or captured,
            "captured_at": captured,
            "content_hash": curator_pre.content_hash(entry.body),
            "external_untrusted": True,          # 污染標籤:內容是資料非指令
            "topic": topic,
            "tags": ["inbox"],
            "summary": (entry.title or topic)[:120],
        }
        ltm.write_note(vault, "semantic", title=entry.title or topic,
                       body=entry.body, frontmatter=frontmatter, ts=ts)
        landed += 1
    stm.event_append(db, "scout", "completed",
                     f"fetched {landed} entries for '{topic}' from {source_url}")
    return {"landed": landed, "rejected": None}


# ── run:觸發收集 + 抓取迴圈(part-008-slice-002)────────────────────────

def has_knowledge_gap(db: Path | None, topic: str, vault: Path) -> bool:
    """粗略知識缺口判定(確定性,無 LLM):vault registry 中無任何筆記的 topic /
    summary / title 提到此主題 → 視為缺口。保守——寧可漏抓不亂抓。"""
    from core import ltm
    needle = topic.strip().lower()
    if not needle:
        return False
    for entry in ltm.registry_entries(vault):
        hay = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
        if needle in hay:
            return False
    return True


def collect_triggers(db: Path | None, vault: Path,
                     now_ts: int | None = None) -> list[dict]:
    """收集本次應研究的目標(確定性):

    1. watchlist 到期主題(主要來源)。
    2. goal facet(part-007)有知識缺口 **且** 該 goal 有對應的 active watchlist
       來源 → 提前研究(不憑空造 URL:必須已有信任來源訂閱)。

    回 [{topic, source_url, watch_id?}];受 SCOUT_MAX_PER_RUN 上限。
    """
    now = now_ts if now_ts is not None else stm.now()
    triggers: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for w in due_watchlist(db, now_ts=now):
        key = (w["topic"], w["source_url"])
        if key not in seen:
            triggers.append({"topic": w["topic"], "source_url": w["source_url"],
                             "watch_id": w["id"]})
            seen.add(key)

    # 知識缺口:goal facet 主題若有對應 active watchlist 來源且 vault 查不到
    active_watch = {w["topic"]: w for w in stm.watchlist_list(db, state="active")}
    for facet in stm.facet_list(db, facet_class="goal"):
        topic = facet["value"]
        w = active_watch.get(topic)
        if w is None:
            continue
        if has_knowledge_gap(db, topic, vault):
            key = (w["topic"], w["source_url"])
            if key not in seen:
                triggers.append({"topic": w["topic"], "source_url": w["source_url"],
                                 "watch_id": w["id"]})
                seen.add(key)

    return triggers[:config.SCOUT_MAX_PER_RUN]


def run(db: Path | None = None, vault: Path | None = None,
        fetcher=None, now_ts: int | None = None) -> dict:
    """完整 scout job:收集觸發 → 逐個 fetch_and_land → 標 watchlist touched。

    只在觸發條件成立時抓(無觸發 → 零抓取)。fetcher 預設 RSS(真網路);
    測試注入 mock。抓來的知識落 inbox,由後續 curate job 評分入庫(不在此鏈)。
    """
    vault = vault or config.VAULT_PATH
    now = now_ts if now_ts is not None else stm.now()
    if fetcher is None:
        from skills.web_fetch import rss
        fetcher = rss.fetch

    from core import ltm
    ltm.init_vault(vault)

    triggers = collect_triggers(db, vault, now_ts=now)
    stats = {"triggers": len(triggers), "landed": 0}
    for t in triggers:
        r = fetch_and_land(db, vault, t["source_url"], t["topic"], fetcher,
                           now_ts=now)
        stats["landed"] += r["landed"]
        if t.get("watch_id"):
            stm.watchlist_touch_checked(db, t["watch_id"], now_ts=now)
    return stats
