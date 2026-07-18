"""Discord bot 薄 adapter(part-002.5;INTERFACES §4)。

鐵律:零業務邏輯——只把 Discord 事件橋接到 core.chat,把 chat.Reply 轉成 Discord
訊息/按鈕。所有解析/驗證/落地在 core;bot 無狀態(待確認提案在 DB1)。

discord.py 延遲 import(run 內):模組本身可在未裝 discord.py 時 import,
純函式(白名單/custom_id 編解碼)可單元測試。
"""

from __future__ import annotations

import os

import config
from core import chat
from core.application import InvocationContext, invoke

# 按鈕 custom_id 前綴:'mycfg:<pending_id>:<y|n>'
_CUSTOM_PREFIX = "mycfg"


# ── 純函式(可單元測試,零 discord 依賴)──────────────────────────────

def allowed_user_ids() -> set[int]:
    """從環境變數讀白名單(逗號分隔)。空 = 拒絕全部(fail-closed)。"""
    raw = os.environ.get(config.DISCORD_ALLOWED_USER_ID_ENV, "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def is_authorized(user_id: int, allowed: set[int]) -> bool:
    """白名單為空 → 全拒(fail-closed,同 Hermes user authorization)。"""
    return bool(allowed) and user_id in allowed


def encode_custom_id(pending_id: int, approve: bool) -> str:
    # pending_id 是 DB AUTOINCREMENT,永遠 ≥1;顯式化契約使 encode/decode 對稱
    if pending_id < 1:
        raise ValueError(f"pending_id must be positive: {pending_id}")
    return f"{_CUSTOM_PREFIX}:{pending_id}:{'y' if approve else 'n'}"


def decode_custom_id(custom_id: str) -> tuple[int, bool] | None:
    """解析按鈕 custom_id → (pending_id, approve)。非本 bot 的 → None。"""
    parts = custom_id.split(":")
    if len(parts) != 3 or parts[0] != _CUSTOM_PREFIX or not parts[1].isdigit():
        return None
    if parts[2] not in ("y", "n"):
        return None
    return int(parts[1]), parts[2] == "y"


def token() -> str:
    tok = os.environ.get(config.DISCORD_TOKEN_ENV)
    if not tok:
        raise RuntimeError(
            f"{config.DISCORD_TOKEN_ENV} 未設。設環境變數後再啟動 bot。")
    return tok


# ── Discord 執行(延遲 import discord.py)──────────────────────────────

def build_client():
    """建立 discord.Client + 事件處理。discord.py 在此才 import。"""
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    client = discord.Client(intents=intents)
    allowed = allowed_user_ids()

    def _confirm_view(pending_id: int):
        view = discord.ui.View(timeout=chat.CONFIRM_TTL_SECONDS)
        for label, approve in (("✅", True), ("❌", False)):
            btn = discord.ui.Button(
                label=label, custom_id=encode_custom_id(pending_id, approve))
            view.add_item(btn)
        return view

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if not is_authorized(message.author.id, allowed):
            return  # 非白名單靜默忽略(私人 bot,§4.1)
        # 裂縫1:走統一入口 application.invoke — Discord 也記 agent_runs,且與
        # CLI/MCP 同一分派。allow_recall=False:知識查詢不經 Discord(§4.1 內容分級)。
        result = invoke(
            str(message.content),
            InvocationContext(trigger="chat", allow_recall=False,
                              channel_ref=str(message.author.id)))
        view = _confirm_view(result.pending_id) if result.needs_confirmation else None
        await message.channel.send(result.text, view=view)

    @client.event
    async def on_interaction(interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if not is_authorized(interaction.user.id, allowed):
            return
        decoded = decode_custom_id(interaction.data.get("custom_id", ""))
        if decoded is None:
            return  # 非本 bot 的按鈕
        pending_id, approve = decoded
        reply = chat.confirm(pending_id, approve)
        await interaction.response.send_message(reply.text)

    return client


async def send_dm(user_id: int, text: str) -> None:
    """提醒 DM 推播(job_remind 的 notify_fn 用)。獨立短連線。"""
    import discord
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            user = await client.fetch_user(user_id)
            await user.send(text)
        finally:
            await client.close()

    await client.start(token())


def run() -> None:
    """啟動常駐 bot(阻塞)。"""
    build_client().run(token())


if __name__ == "__main__":
    run()
