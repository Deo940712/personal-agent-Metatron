# threads-sync

把你在 **Threads 上「已儲存」的貼文**，自動同步成 **Obsidian 知識庫**的工具。

Threads 的儲存清單是個黑洞——存了就再也不會回去看，官方也不提供匯出。這個工具把它變成一個可搜尋、可分類、圖片永久保存、離線可用的個人知識庫，並且為 AI 助手（Claude 等）設計了完整的管理規則。

## 它做了什麼

```
Threads 已儲存貼文
   │  Playwright + 你自己的登入 session
   │  攔截 GraphQL response（不刮 DOM）
   ▼
每篇貼文 → 一個 Markdown 筆記
   ├─ frontmatter：作者、原文連結、日期、按讚數、分類 tag
   ├─ 內文：完整文字，網址自動轉可點連結
   ├─ 串文：作者的多則接續自動合併成一篇（~半數貼文是串文）
   └─ 圖片：下載到本地 attachments/（CDN 網址會過期，不下載就沒了）
   ▼
Obsidian vault
   ├─ 自動分類成 14 個主題 tag
   └─ _index/ 自動生成分類索引（MOC），按讚數排序
```

### 主要特性

- **增量同步**：SQLite 以 post_id 去重，第二次跑只抓新貼文；中斷後 cursor 續傳
- **串文合併**：Threads 作者常把內容拆成 2-17 則接續串文。saved 列表的 API 只給第一則——本工具會開貼文頁、從 SSR 的 inline JSON 抽出作者全部接續（排除別人的留言），合併成完整筆記
- **連結重建**：`caption.text` 的網址常被截斷成 `github.com/allen…`，本工具從 `text_fragments` 重建成完整可點的 Markdown 連結
- **圖片落地**：885 張圖這種量級實測過。Meta CDN 網址幾天就過期，全部下載到 `vault/attachments/` 用相對路徑引用，離線可用
- **自動分類**：關鍵字計分把筆記歸入 14 類（AI Agent、Claude、本地 LLM、前端、DevOps…），手動改過的 tag 永不覆蓋
- **AI 管理規則**：`vault/CLAUDE.md` 定義了 AI 助手整理知識庫的完整規範（分類體系、硬規則、標準任務 SOP）
- **低調運作**：所有請求帶隨機延遲，不高頻、不規避偵測、像正常使用

## 為什麼不用官方 API / 現成爬蟲？

- Threads 官方 API 不開放讀取「已儲存」清單（那是私人資料）
- 事後批次爬蟲長期不穩、有帳號風險
- 本工具的策略：**帶自己 session 的瀏覽器 + 只抓增量 + 資料落地後不再依賴 Threads**

## 架構

```
threads-sync/
├── sync.py            # 1. 爬新貼文 → vault .md（орchestrator）
├── sync_threads.py    # 2. 串文回填：合併作者接續
├── sync_media.py      # 3. 圖片下載 → attachments/
├── classify.py        # 4. inbox 筆記自動分類
├── build_moc.py       # 5. 重建 _index/ 分類索引
├── browser.py         # Playwright persistent session + GraphQL 攔截
├── transform.py       # normalize / 連結重建 / 串文抽取 / Markdown 渲染
├── store.py           # SQLite：去重、串文狀態、圖片狀態、cursor 續傳
├── media.py           # 圖片下載器（idempotent、失敗重試）
├── config.py          # 所有路徑與參數（換機器只改這裡）
├── import_session.py  # 從真實 Chrome 匯入登入 session（一次性）
├── phase0_probe.py    # 探勘工具：dump saved 列表的 GraphQL
└── probe_thread.py    # 探勘工具：dump 單篇貼文頁的 GraphQL + HTML
```

資料流：**Capture**（攔 GraphQL）→ **State**（SQLite 判斷新舊）→ **Transform**（normalize + Markdown）→ **Output**（寫 vault + 下圖）。

## 安裝

需求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、Windows（Linux 亦可，改 `config.py` 路徑即可）

```bash
uv sync
uv run playwright install chromium
```

## 登入設定（一次性，最關鍵的一步）

**不能**直接在 Playwright 裡登入——Meta 的 anti-scripting reCAPTCHA 會擋。改用匯入真實瀏覽器 session：

1. 用你平常的 Chrome 登入 <https://www.threads.com>
2. 安裝 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 擴充
3. 在 Threads 分頁：Cookie-Editor → Export → JSON；在 <https://www.instagram.com> 分頁再匯出一次（Threads 用 IG 帳號系統），兩份合併成一個 `cookies.json`
4. 匯入：

```bash
uv run python threads-sync/import_session.py cookies.json
```

看到 `SUCCESS: session looks authenticated` 即完成。session 存在 `data/playwright/`，之後不用重登。

> ⚠️ `cookies.json` 和 `data/playwright/` 含登入憑證，已在 `.gitignore` 排除，**絕不要 commit**。

## 使用

### 例行同步（依序執行）

```bash
uv run python threads-sync/sync.py          # 1. 抓新的已儲存貼文
uv run python threads-sync/sync_threads.py  # 2. 補作者串文
uv run python threads-sync/sync_media.py    # 3. 下載圖片
uv run python threads-sync/classify.py      # 4. 自動分類新筆記
uv run python threads-sync/build_moc.py     # 5. 重建分類索引
```

每一步都是 idempotent——已處理的自動跳過、中斷了重跑會續傳。步驟 1-3 會開瀏覽器視窗（帶著已登入 session）。

### 打開知識庫

用 [Obsidian](https://obsidian.md) 開 `vault/` 資料夾。入口是 `_index/00-總索引`，14 個分類各有一頁 MOC，筆記按讚數排序。

### 搭配 AI

`vault/CLAUDE.md` 內建了 AI 管理規則。用 Claude Code 等工具開 vault 資料夾，直接說：

- 「照規則清 inbox」→ 自動分類新筆記
- 「總結 RAG 相關筆記」→ 產出主題總結
- 「我存過哪些簡報工具？」→ 全庫查詢

## 輸出格式

每篇筆記長這樣：

```markdown
---
source: threads
author: "作者帳號"
url: https://www.threads.com/@作者/post/XXXX
date: 2026-06-30 10:27
likes: 112
tags:
  - threads
  - ai-agents
---

主貼內文……網址是[可點的](https://example.com)

---

作者的第二則接續……

![image](attachments/3930601122847864089_1.jpg)

[原始貼文](https://www.threads.com/@作者/post/XXXX)
```

## 技術筆記（逆向發現）

開發過程釘死的幾個關鍵事實，記錄在 `AGENTS.md`：

- saved 列表走 `POST /graphql/query`（`/api/graphql` 會回 anti-scripting 等待頁）
- response 路徑：`data.xdt_text_app_viewer.saved_media.edges[]`，分頁靠 `page_info.end_cursor`
- **串文接續不在任何 GraphQL 裡**——它是 SSR 直接嵌在貼文頁 HTML 的 `<script type="application/json">`。判斷作者接續：`user.pk == 主貼作者` 且有 `post_position_in_self_thread`
- `media_type`：1=圖、2=影片、8=多圖輪播、19=文字附連結卡

## 風險與界線

- Meta ToS 禁止自動化抓取，屬灰色地帶，自行評估。本工具刻意低頻、增量、不做偵測規避
- 抓的是**你自己帳號的私人儲存清單**，資料自用
- GraphQL 介面改版時工具會壞——`sync_runs` 表的 status 欄是主要偵測點，探勘工具（`phase0_probe.py` / `probe_thread.py`）可快速重新定位 schema

## License

MIT
