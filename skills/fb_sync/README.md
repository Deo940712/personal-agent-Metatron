# fb-sync

把你在 **Facebook「已儲存」的貼文**同步成 Obsidian 知識庫（同 threads-sync 架構）。

## 狀態（2026-07-17）

| 部分 | 狀態 |
|---|---|
| Phase 0 探勘（釘死 schema） | ✅ 完成 |
| 管線程式（transform/store/browser/sync） | ✅ 完成，24 tests 綠、離線端到端過 |
| **實跑抓取** | ⚠️ **被 FB 反爬降級**（見下），隔段時間恢復後再跑 |

**實跑當下 FB 不回傳 saved GraphQL**（連探勘腳本也抓不到）——這是 FB 對重複自動化
存取的降級行為，非程式 bug。**通常隔幾小時/隔天會恢復**。管線已就緒，恢復後直接能抓。

## Phase 0 探勘釘死的 schema（已驗證）

- **資料入口**：`/saved` 主頁只是導覽面板；真資料在特定 collection 的
  `https://www.facebook.com/saved/?list_id=<LIST_ID>&referrer=SAVE_DASHBOARD_NAVIGATION_PANEL`。
  滾動它才觸發 `content_collection` GraphQL。
- **端點**：`POST /api/graphql/`（多查詢共用；靠 response 有無 `content_collection` 區分）
- **列表**：`data.content_collection.collection_items.edges[].node`
- **分頁**：`collection_items.page_info.end_cursor` + `has_next_page`
- **欄位**：
  - `node.savable.id` — 貼文 id（dedupe key；可能含冒號 → 檔名需清）
  - `node.savable.savable_title.text` — 內文
  - `node.savable.savable_permalink` / `node.savable.story.url` — 原文連結
  - `node.savable.savable_image.uri` — 圖片（fbcdn，會過期 → media 階段下載）
  - `node.savable.savable_default_category` — POST_WITH_PHOTO 等
  - `node.saver.name` / `.profile_url` — 存貼文的人（=你）

## 登入設定（一次性）

FB 也擋 Playwright 內登入，改匯入真實 Chrome 的 cookie：

1. Chrome 登入 <https://www.facebook.com>（**建議用次要帳號**——FB 封鎖快）
2. Cookie-Editor → FB 分頁 → Export → JSON（關鍵 cookie：`c_user` + `xs`）
3. `python import_session.py <cookies.json>`

## 使用

```bash
# 設你的 saved collection list_id（從瀏覽器 saved 頁 URL 取；預設已填一個）
set FB_SYNC_LIST_ID=<你的 list_id>

# 抓已儲存貼文 → fb_vault/*.md
python sync.py
```

`FB_SYNC_HEADLESS=1` 無頭跑；預設 headed 可看瀏覽器。增量：SQLite 以 id 去重、
cursor 續傳，第二次只抓新的。

## 若實跑抓到 0 篇（FB 降級）

1. **隔段時間再試**（幾小時/隔天）——FB 降級多會恢復。
2. 或改 headed（拿掉 `FB_SYNC_HEADLESS`），手動在視窗點進 saved collection、
   手動滾動觸發資料，crawl 在背景攔。
3. 重新探勘定位 schema：`python run_probe.py "<collection URL>" 12`
   → 看 `fb_data/raw/` 有無含 `content_collection` 的 dump。

## 架構（同 threads-sync）

```
config.py          所有路徑/URL/參數
browser.py         Playwright session + GraphQL 攔截 + cookie 匯入
import_session.py  一次性 FB cookie 匯入
phase0_probe.py    探勘：dump saved 頁的 network（run_probe.py 是非互動版）
transform.py       node → normalize → Markdown
store.py           SQLite：去重(id) + cursor 續傳 + sync_runs
sync.py            orchestrator：爬 collection → dedupe → vault .md
tests/             transform/store/sync 測試（真 dump fixture）
```

未做（threads-sync 有、fb 待補）：media 下載、classify 分類、build_moc 索引、
串文（FB saved 非自我串文結構，不需要）。

## 風險

FB ToS 禁自動化抓取；反爬比 Threads 嚴、降級/封鎖快。原則：低頻、增量、
不做偵測規避、用次要帳號。抓的是你自己帳號的私人 saved，資料自用。
