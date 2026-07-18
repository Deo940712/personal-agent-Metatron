"""Taiwan-retail stock domain pack — the original 10 archetypes, now as a DomainPack.

This is the reference pack: it reproduces the engine's original hard-coded Taiwan
stock behaviour verbatim (same personas, herding, voices, sensitivities, tilts), now
expressed through the domain-agnostic ``DomainPack`` protocol. Two ordinal axes:
``discount_premium`` (cheapness) and ``yield``. The neutral CONSENSUS vocabulary is
rendered back to finance display labels via ``consensus_display``.

Persona roster / priors: see ``references/personas.md``.
"""

from __future__ import annotations

from crowdscenario.domains.base import Axis, DomainPack


def bucket_discount_premium(x: float) -> str:
    if x <= -1.0:
        return "deep_discount"
    if x < -0.1:
        return "discount"
    if x <= 0.1:
        return "fair"
    if x < 1.0:
        return "premium"
    return "rich"


def bucket_yield(x: float) -> str:
    if x < 3.0:
        return "low"
    if x <= 6.0:
        return "normal"
    return "high"


_DISCOUNT_TILT = {
    "deep_discount": 1.0,
    "discount": 0.5,
    "fair": 0.0,
    "premium": -0.5,
    "rich": -1.0,
}
_YIELD_TILT = {"low": -1.0, "normal": 0.0, "high": 1.0}


STOCK_TW = DomainPack(
    domain_id="stock_tw",
    persona_ids=(
        "long_term_holder",
        "day_trader",
        "yield_seeker",
        "leveraged_etf_player",
        "foreign_institutional_lens",
        "panic_retail",
        "ptt_dcard_trendwatch",
        "mom_savings_group",
        "main_force_lens",
        "dca_newbie",
    ),
    contra_ids=frozenset(
        {
            "long_term_holder",
            "foreign_institutional_lens",
            "mom_savings_group",
            "main_force_lens",
        }
    ),
    herding={
        "long_term_holder": 0.15,
        "day_trader": 0.85,
        "yield_seeker": 0.40,
        "leveraged_etf_player": 0.70,
        "foreign_institutional_lens": 0.10,
        "panic_retail": 0.90,
        "ptt_dcard_trendwatch": 0.95,
        "mom_savings_group": 0.35,
        "main_force_lens": 0.20,
        "dca_newbie": 0.75,
    },
    voice={
        "long_term_holder": {
            1: "續抱不動,反而想趁機加碼撿便宜,股息照領。",
            0: "無所謂短線,部位不動,繼續存。",
            -1: "帳面回檔但不賣,長期持有本來就要耐震。",
        },
        "day_trader": {
            1: "順勢做多、跟動能,但停損設很緊,隔日沖不留倉。",
            0: "區間震盪不好做,先觀望減少進出。",
            -1: "轉空單或空手,破前低就跑,絕不凹單。",
        },
        "yield_seeker": {
            1: "殖利率誘人,除息前想卡位領息、賭填息。",
            0: "配息看得順眼才動,現在再等等看。",
            -1: "擔心貼息與配息縮水,先減碼避風頭。",
        },
        "leveraged_etf_player": {
            1: "波動就是機會,加槓桿做多、放大部位。",
            0: "盤整最傷槓桿(每日重設耗損),暫時退場。",
            -1: "怕連續下跌被複利吃掉,快速停損出場。",
        },
        "foreign_institutional_lens": {
            1: "看基本面與指數權重,逢低分批布局。",
            0: "等法說會與數據,按兵不動。",
            -1: "調節部位、對沖風險,不追殺也不接刀。",
        },
        "panic_retail": {
            1: "看到大家在買、怕錯過,追高進場。",
            0: "看不懂方向,先抱著不動。",
            -1: "看到黑K就恐慌,殺在最低點。",
        },
        "ptt_dcard_trendwatch": {
            1: "看板風向轉多,發文喊進、氣氛熱絡。",
            0: "討論度冷清,沒什麼人在推。",
            -1: "看板一片哀嚎,風向轉空、互相勸退。",
        },
        "mom_savings_group": {
            1: "群組互相打氣,續扣定期定額還加碼。",
            0: "照計畫定期定額,不看盤不改單。",
            -1: "越跌越買、當作打折,扣款照舊不停扣。",
        },
        "main_force_lens": {
            1: "低調吸籌、分批進場,不驚動散戶。",
            0: "量能不足,按兵不動觀察籌碼。",
            -1: "趁人氣高出貨、調節持股,先落袋。",
        },
        "dca_newbie": {
            1: "剛開始扣款、興奮加碼,近因偏誤明顯。",
            0: "小額試單,還在學怎麼看。",
            -1: "第一次遇到回檔就緊張,考慮暫停扣款。",
        },
    },
    display_name={
        "long_term_holder": "存股族",
        "day_trader": "當沖客",
        "yield_seeker": "殖利率派",
        "leveraged_etf_player": "槓桿 ETF 玩家",
        "foreign_institutional_lens": "外資視角",
        "panic_retail": "恐慌散戶",
        "ptt_dcard_trendwatch": "PTT/Dcard 風向",
        "mom_savings_group": "媽媽存股社團",
        "main_force_lens": "主力/中實戶",
        "dca_newbie": "定期定額新手",
    },
    axes=(
        Axis(name="discount_premium", bucket_fn=bucket_discount_premium, tilt=_DISCOUNT_TILT),
        Axis(name="yield", bucket_fn=bucket_yield, tilt=_YIELD_TILT),
    ),
    sensitivity={
        "long_term_holder": (0.8, 0.4),
        "day_trader": (0.0, 0.0),
        "yield_seeker": (0.2, 1.0),
        "leveraged_etf_player": (0.0, 0.0),
        "foreign_institutional_lens": (0.7, 0.2),
        "panic_retail": (0.0, 0.0),
        "ptt_dcard_trendwatch": (0.0, 0.0),
        "mom_savings_group": (0.6, 0.5),
        "main_force_lens": (0.9, 0.1),
        "dca_newbie": (0.1, 0.1),
    },
    consensus_display={
        "negative": "bearish",
        "neutral": "neutral",
        "positive": "bullish",
    },
    horizon_frame={"intraday": "當日盤中", "swing": "波段", "long": "長線"},
    # Demonstration voice variants for two high-herding, high-emotion cohorts: the engine
    # picks one deterministically by seed hash, so two scenarios read differently while
    # each stays reproducible. Personas without variants fall back to their single voice.
    voice_variants={
        "panic_retail": {
            1: (
                "看到大家在買、怕錯過,追高進場。",
                "群組一直喊、深怕少賺,忍不住就跟著追。",
                "看紅就手癢,擔心錯過波段,衝動加碼。",
            ),
            -1: (
                "看到黑K就恐慌,殺在最低點。",
                "越跌越慌、越慌越賣,砍在阿呆谷。",
                "看到帳面縮水就睡不著,認賠了結求安心。",
            ),
        },
        "ptt_dcard_trendwatch": {
            1: (
                "看板風向轉多,發文喊進、氣氛熱絡。",
                "推文一片看好,鄉民開始揪團上車。",
                "版上帶風向做多,樂觀情緒發酵。",
            ),
            -1: (
                "看板一片哀嚎,風向轉空、互相勸退。",
                "推文開始檢討,鄉民互相提醒別接刀。",
                "版上氣氛急凍,看空文洗版。",
            ),
        },
    },
)
