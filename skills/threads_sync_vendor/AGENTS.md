# AGENTS.md

## What this repo is

Greenfield project: an **incremental sync tool** that pulls the user's *saved* Threads posts via a Playwright session and writes them as frontmatter-tagged Markdown into an Obsidian vault. No code exists yet — the full spec lives in [threads-sync-plan.md](threads-sync-plan.md) (zh-TW). **Read that plan before implementing anything**; it holds the design decisions below.

Not a git repo. `.codegraph/` is external tooling, not project code — ignore it.

## Non-obvious design rules (do not violate)

- **Incremental, not full-scan.** Saved posts are newest-first. Scroll from the top; stop after `STOP_AFTER_SEEN` *consecutive* already-known `post_id`s (not the first hit — user may have un-saved a few mid-list).
- **Capture GraphQL responses, do NOT scrape the DOM.** Intercept the GraphQL `response` fired when the saved tab loads/scrolls, and read JSON. Parsing React DOM is explicitly rejected.
- **All paths go through `config.py`.** Never hardcode `C:\Users\...` or `/home/...`. The project is developed on Windows and later moved to Linux; the only intended change is `config.py`.
- **Media must be downloaded locally.** Threads CDN image URLs expire. Save images to the vault's `attachments/` and reference relative paths in the `.md`.
- **Append-only.** Un-saved posts stay in the vault/DB (at most flag in SQLite). Never delete synced content.
- **Session persistence.** Use Playwright **persistent context** with a fixed user data dir (`data/playwright/`). First login is manual, on Windows, headed.
- **Low frequency, jittered.** Add randomness to `SCROLL_DELAY`; no fixed on-the-hour full scans. Don't add anti-detection evasion.

## Planned structure (create as you build)

```
threads-sync/
├── sync.py        # orchestrator / entrypoint
├── browser.py     # Playwright persistent session + GraphQL capture
├── store.py       # SQLite dedupe (post_id) + stop-on-seen
├── transform.py   # normalize() + to_markdown()
├── media.py       # download images to vault attachments/
├── config.py      # ALL paths + params live here
└── data/          # state.db, raw/ (dumped responses), playwright/ (session)
```

`config.py` params: `VAULT_PATH`, `USER_DATA_DIR`, `DATA_DIR`, `HEADLESS`, `STOP_AFTER_SEEN`, `SCROLL_DELAY`.

## Build order (phased — respect it)

Do the earlier phase first; each has a completion gate in the plan.

- **Phase 0 (DONE):** schema pinned down — see the verified schema section below.
- **Phase 1 (DONE, pending live run):** `sync.py` crawls all saved posts (paginates to
  `has_next_page=False`), `transform.py` renders each to `.md`. Already dedupes via
  `store.py` and persists `crawl_state.end_cursor` per page for resume-on-interrupt.
  Media referenced by remote CDN URL (Phase 3 downloads locally). Validated offline
  against real Phase 0 dumps for media_type 1/2/8/19; live crawl still to be run by user.
- **Phase 2:** stop-on-seen (`STOP_AFTER_SEEN` consecutive knowns) for incremental runs
  — dedupe + cursor already wired; add the early-stop loop.
- **Phase 3:** `media.py` local images + relative paths in `.md`.
- **Phase 4:** scheduling + login-expiry detection (never fail silently) + `sync_runs` logging.

## Login is via imported session, NOT in-Playwright login

Meta's anti-scripting reCAPTCHA blocks logging in *inside* Playwright's Chromium
(`/api/graphql` returns `xfb_auth_platform_anti_scripting_content`). Instead:
log in with real Chrome → export cookies (Cookie-Editor → JSON) → `import_session.py`
injects them via `context.add_cookies()` into the persistent context. `sync.py` /
`phase0_probe.py` then start already authenticated. `import_session.py` checks for the
key cookies `sessionid` + `ds_user_id`.

## Entrypoints (routine sync runs 1-5 in order)

- `sync.py` — 1. crawl new saved posts → vault `.md`. Also flags self-threads
  (`thread_len`) on the pre-existing posts on re-run.
- `sync_threads.py` — 2. backfill pass: merge each self-thread's author continuations
  into its `.md`. Run AFTER `sync.py`.
- `sync_media.py` — 3. download images → `vault/attachments/`, rewrite md to relative
  paths. Videos stay remote by design.
- `classify.py` — 4. tag notes still marked `- inbox` into the 14-tag taxonomy
  (keyword scoring; taxonomy mirrored in `vault/CLAUDE.md` — keep both in sync).
- `build_moc.py` — 5. regenerate `vault/_index/` MOC notes. The "claude" category
  file is `claude-anthropic.md` (naming `claude.md` collides with vault/CLAUDE.md
  on case-insensitive Windows).
- `phase0_probe.py` — saved-list discovery/dump tool (writes `data/raw/` + `manifest.txt`).
- `probe_thread.py [code]` — single-post discovery: dumps a post detail page's GraphQL
  + full HTML to `data/raw/thread/`.
- `import_session.py <cookies.json>` — one-time session import from real Chrome.
- `store.py` (run directly) — init the SQLite DB.

An operator skill (full SOP + troubleshooting) lives at
`~/.claude/skills/threads-sync/SKILL.md`.

## Self-thread continuations live in SSR HTML, NOT GraphQL (verified)

The saved-list response only carries the MAIN post; each edge's `thread_items` has
len 1. ~half of saved posts are self-threads (`post.text_post_app_info.self_thread_info.
self_thread_length` > 1) where the author continues across 2-4 chained posts. That
continuation text is **server-side rendered into the post detail page's inline
`<script type="application/json">` blobs** — opening the post page fires NO GraphQL call
carrying it (only like-count polling `data.data.posts[]`). So to get continuations:
open `https://www.threads.com/@{user}/post/{code}`, read `page.content()`, parse inline
JSON. Path (verified against `page_DaMTOVhGTUZ.html`):
`require[..].__bbox..result.data.data.edges[].node.thread_items[].post`. Identify the
author's own posts by `post.user.pk == main author pk` AND a set
`self_thread_info.post_position_in_self_thread`; order by that position. Other users'
replies appear as sibling edges with a different `user.pk` and `pos = None` — exclude them.
`transform.extract_author_thread(html, author_pk)` implements this.

## In-text links → clickable Markdown

`caption.text` can show truncated/label-only link text with no real URL. Rebuild the
body from `post.text_post_app_info.text_fragments.fragments[]`: plaintext fragments
verbatim, `fragment_type=="link"` fragments as `[link_fragment.display_text](link_fragment.uri)`.
Fallback to `caption.text` when no fragments. `transform.build_body(post)` implements this.

## Saved-posts GraphQL schema (Phase 0 findings — verified)

Endpoint: **`POST https://www.threads.com/graphql/query`** (NOT `/api/graphql`; that one
returns the anti-scripting wait screen). Filter capture on `/graphql/query`. Ignore
`/ajax/bulk-route-definitions/` and `/data/manifest.json` — routing/PWA noise.

A saved-posts response is identified by the presence of
`data.xdt_text_app_viewer.saved_media`. Field paths (verified against real dumps):

- Posts list: `data.xdt_text_app_viewer.saved_media.edges[]`
- Pagination: `saved_media.page_info.end_cursor` + `.has_next_page` (bool)
- Per edge: `edges[].node.thread_items[].post` (thread_items is a list; a single saved
  item usually has len 1, but iterate it).
- `post.pk` = numeric post_id (dedupe key). `post.id` = `"{pk}_{user_id}"`. `post.code`
  = shortcode for the URL: `https://www.threads.com/@{username}/post/{code}`.
- `post.user.username`, `post.user.full_name`, `post.user.is_verified`
- Text: `post.caption.text` (full body). But prefer rebuilding from
  `post.text_post_app_info.text_fragments.fragments[]` to get clickable links — see
  "In-text links" above. `caption.text` is the fallback when no fragments.
- `post.like_count`, `post.taken_at` (unix seconds), `post.detected_language`,
  `post.has_viewer_saved`, `post.accessibility_caption`
- Media: `post.media_type` — observed values **1=image, 2=video, 8=carousel, 19=?**
  (19 still has caption text; treat unknown types as text + best-effort media).
  - Image: `post.image_versions2.candidates[]` (list, largest first — index 0 is
    highest res; pick by width/height).
  - Video: `post.video_versions[]`.
  - Carousel: `post.carousel_media` (list of child media, each with its own
    `image_versions2` / `video_versions`).

CDN image URLs (`*.fbcdn.net`) expire — Phase 3 must download locally.

## Data / output conventions

- SQLite `posts` (PK = Threads `post_id`) tracks dedupe + `media_done`; `sync_runs` tracks each run's `new_count`/`status` (`ok` / `login_expired` / `error`) — this status is the primary breakage detector when GraphQL changes.
- Every `.md` gets an `inbox` tag first (re-classified later in Obsidian). Frontmatter: `source: threads`, `author`, `url`, `date`, `likes`, `tags`. See the plan's section 5 for the exact template.

## Open decisions (ask user if they block you)

First-crawl depth cap (could be thousands of posts — batch?) and un-save handling are noted as "to decide" in the plan.
