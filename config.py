"""所有路徑與參數集中於此(threads-sync 規則:換機器/遷 VPS 只改這個檔案)。

時間欄位一律 UTC epoch 秒 (int)。秘密不放這裡:以 *_ENV 常數指名環境變數。
"""

from pathlib import Path

# ── 資料根目錄(本地、OneDrive 外;遷 VPS 時改這行) ──────────────────
DATA_DIR = Path(r"C:\Users\tcart\my-agent-data")

# ── DB1:System of Record ───────────────────────────────────────────
STATE_DB = DATA_DIR / "state.db"

# ── DB2:Obsidian vault(人類知識介面;part-003 起使用) ─────────────
VAULT_PATH = DATA_DIR / "vault"

# ── 衍生物與原始記錄(part-003 起使用) ──────────────────────────────
INDEX_DB = DATA_DIR / "index.db"          # 向量索引(可整檔刪除重建)
TRANSCRIPT_DIR = DATA_DIR / "transcript"  # 冷儲存 JSONL + .idx

# ── 秘密(以環境變數名引用,值不落地 repo) ──────────────────────────
DISCORD_TOKEN_ENV = "MY_AGENT_DISCORD_TOKEN"           # Phase 2.5
DISCORD_ALLOWED_USER_ID_ENV = "MY_AGENT_DISCORD_ALLOWED_USER_ID"  # 白名單(逗號分隔)
LLM_API_KEY_ENV = "MY_AGENT_LLM_API_KEY"       # Phase 2

# ── MCP HTTP 傳輸(part-006-slice-003;VPS 後遠端 OpenCode) ────────────
# 綁定介面 IP。未設 = 127.0.0.1(本機)。VPS 上設為 Tailscale IP(100.64.0.0/10)。
# 綁公網 IP → 啟動拒絕(fail-closed;Tailscale 已是 WireGuard 加密私網,不需 token/TLS)。
MCP_BIND_HOST_ENV = "MY_AGENT_MCP_BIND_HOST"
MCP_HTTP_PORT = 7788                            # MCP HTTP 傳輸埠(stdio 無埠)

# ── LLM(OpenAI 相容 API;backlog-002 定案) ─────────────────────────
LLM_BASE_URL_ENV = "MY_AGENT_LLM_BASE_URL"     # 未設 = OpenAI 官方
LLM_MODEL_CHEAP = "gpt-5.5"                # bounded 任務:分類/抽取/格式化
LLM_MODEL_STRONG = "gpt-5.5"                    # 綜合與決策(orchestrator)

# ── 記憶系統(part-003;docs/MEMORY-zh.md §3) ───────────────────────
HEALTH_DECAY_PER_DAY = 0.05                    # 線性日衰減(1.0 → 0 需 20 天)
TRASH_RETENTION_DAYS = 14                      # trash 保留期(期內被引用可復活)
DISTILL_MIN_CONFIDENCE = 0.6                   # 蒸餾決策低於此即跳過
CURATE_SCORE_THRESHOLD = 4.0                   # curator 評分閘門(低於=只留 metadata)
CURATE_BATCH_SIZE = 10                         # curator 每批筆記數
CURATE_TAG_QUOTA = 20                          # 單次 curate 每 tag 進 registry 上限(防洪水)
EMBED_MODEL = "text-embedding-3-small"         # OpenAI 相容 /v1/embeddings
EMBED_DIM = 1536
EMBED_BASE_URL_ENV = "MY_AGENT_EMBED_BASE_URL" # 未設 = 同 LLM_BASE_URL

# ── 個人模型 facets(part-007;初值保守,真實使用 1-2 月有數據再調) ────
FACET_STABLE_MIN_EVIDENCE = 3                  # provisional → stable 最少證據次數
FACET_STABLE_MIN_DAYS = 3                      # 證據須橫跨的最少天數(防單日洗量)

# ── 主動建議 advisor(part-009;防疲勞初值保守) ──────────────────────
ADVICE_DAILY_QUOTA = 3                          # 每日 advice 產出上限(防噪音)
ADVICE_DEDUP_WINDOW_DAYS = 3                    # 同 dedup_key 幾天內不重推
ADVICE_DEFAULT_TTL_DAYS = 3                     # advice 預設過期天數(LLM 未給時)
ADVICE_PUSH_MIN_PRIORITY = "medium"            # 只主動推 medium/high(low 查詢時才顯示)

# ── 情境演練 crowd-scenario(part-010;vendored 黑箱,subprocess 隔離) ────
# vendored src 路徑(PYTHONPATH);pin commit 見 skills/crowd_scenario_vendor/VENDORED.md。
CROWD_SCENARIO_SRC = Path(__file__).parent / "skills" / "crowd_scenario_vendor" / "src"
SCENARIO_DEFAULT_N = 24                          # 每次演練 persona 數(成本控制)

# ── 知識偵察 scout(part-008;網路內容=不受信任資料,非指令) ────────────
# allowlist:只准這些網域(含子網域)抓取;不在清單 = fail-closed 拒絕。
# 空清單 = 全拒(必須顯式加入信任來源才能研究)。起步用穩定 RSS/結構化來源。
SCOUT_ALLOWLIST_DOMAINS = [
    "arxiv.org", "github.com", "news.ycombinator.com",
]
SCOUT_MAX_PER_RUN = 5                            # 每次研究抓取上限(成本控制)
SCOUT_MIN_INTERVAL_DAYS = 1                      # watchlist 最低複查間隔(下限守衛)
