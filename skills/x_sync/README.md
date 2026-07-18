# x-sync

把你在 **X (Twitter) 按讚的貼文**（likes）同步成 Obsidian 知識庫。

> 原目標是 bookmarks,但實測該帳號 bookmarks 空、likes 有內容,故目標定為 **likes**。
> bookmarks 端點程式也在(schema 類似),需要時可切換。

## 狀態（2026-07-18）

| 部分 | 狀態 |
|---|---|
| Phase 0 探勘（釘死 schema） | ✅ 完成 |
| 管線程式（transform/store/browser/sync） | ✅ 完成,**24 tests 綠**、離線端到端過 |
| **實跑抓取** | ✅ **成功**——抓到 5 篇 likes → 5 個 .md（真 permalink、frontmatter 完整） |

### 實跑踩到的雷（已修,記錄供參考）

1. **監聽層**:X 的 likes GraphQL 可能在別 frame 觸發,必須用 `page.context.on`
   而非 `page.on`（page 層攔 0,context 層攔到 5）。
2. **觸發時機**:X 的 Likes GraphQL 是**第一次滾動才發**（初始 goto 不發資料）。
   `iter_like_pages` 的迴圈必須「先滾動→等待→drain」,否則在資料到達前就累積
   empty_streak 提早退出 → 0 posts。這是實跑一直 0 篇的根因。

## Phase 0 探勘釘死的 schema（真 dump 驗證）

- **資料入口**：`x.com/<username>/likes`,滾動觸發 GraphQL `/Likes`。
- **端點**：`GET /i/api/graphql/<id>/Likes`（多查詢共用 `/i/api/graphql/`；靠 response
  有無 `user.result.timeline` 的 `TimelineAddEntries` 區分）
- **timeline**：`data.user.result.timeline.timeline.instructions[]`（type=TimelineAddEntries）
- **tweet**：`entries[]`（entryId=`tweet-<id>`）→ `content.itemContent.tweet_results.result`
  - `rest_id` — tweet id（dedupe key）
  - `legacy.full_text` — 內文
  - `legacy.created_at` — 時間
  - `legacy.extended_entities.media[].media_url_https` — 圖片
  - **`core.user_results.result.core.screen_name` / `.name`** — 作者
    （⚠️ 新版 X 在 `.core`,不是舊逆向文件說的 `.legacy`——真 dump 校正過）
- **分頁**：entryId=`cursor-bottom-...` → `content.value`

## 登入設定（一次性）

X 也建議匯入真實 Chrome 的 cookie（比 Playwright 內登入穩）：

1. Chrome 登入 <https://x.com>
2. Cookie-Editor → x.com 分頁 → Export → JSON（關鍵 cookie：`auth_token` + `ct0`）
3. `python import_session.py <cookies.json>`

## 使用

```bash
# 設你的用戶名（likes 頁 = x.com/<username>/likes）
set X_SYNC_USERNAME=<你的用戶名>

# 抓 likes → x_vault/*.md
python sync.py
```

`X_SYNC_HEADLESS=1` 無頭跑;預設 headed。增量:SQLite 以 tweet id 去重、cursor 續傳。

## 架構（同 threads/fb-sync）

```
config.py          所有路徑/URL/參數（likes URL + username）
browser.py         Playwright session + Likes GraphQL 攔截 + cookie 匯入
import_session.py  一次性 X cookie 匯入
phase0_probe.py    探勘（run_probe.py 是非互動版）
transform.py       tweet result → normalize → Markdown（extract_timeline/tweets/cursor）
store.py           SQLite：去重(tweet id) + cursor 續傳 + sync_runs
sync.py            orchestrator：爬 likes → dedupe → vault .md
tests/             transform/store/sync 測試（真 dump fixture,7 entries/5 tweets）
```

未做（threads-sync 有、x 待補）：media 下載、classify 分類、build_moc 索引。

## 風險

X 對讀自己 likes 相對寬鬆（比 FB 好抓）。原則同其他 sync：低頻、增量、
不做偵測規避。抓的是你自己帳號的 likes,資料自用。
