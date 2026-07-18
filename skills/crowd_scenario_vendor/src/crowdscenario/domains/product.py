"""Product-launch domain pack — a non-finance domain that exercises the skeleton.

This proves the engine is domain-agnostic: a different persona roster, a DIFFERENT
number of ordinal axes (three, vs the stock pack's two), and its own display labels
(oppose / neutral / support), all plugged in through the same ``DomainPack`` protocol
and the same firewall. No finance concept leaks in.

Scenario: an already-decided product change (a new feature, a price hike, a redesign).
The synthetic crowd rehearses how eight user cohorts react — again narrative only, no
number, no decision write-back.

Three ordinal axes:
- ``price_change``   — how the change hits the wallet (cut → hike).
- ``value_delta``    — perceived usefulness of the change (worse → better).
- ``switching_cost`` — how locked-in the cohort is (low → high; high lock-in fades revolt).
"""

from __future__ import annotations

from crowdscenario.domains.base import Axis, DomainPack


def bucket_price_change(x: float) -> str:
    """Relative price move: negative = cheaper, positive = pricier."""
    if x <= -0.15:
        return "cut"
    if x < 0.05:
        return "flat"
    if x < 0.25:
        return "hike"
    return "steep_hike"


def bucket_value_delta(x: float) -> str:
    """Perceived value change of the release in roughly [-1, +1]."""
    if x <= -0.3:
        return "worse"
    if x < 0.3:
        return "same"
    return "better"


def bucket_switching_cost(x: float) -> str:
    """How hard it is for the cohort to leave, in roughly [0, 1]."""
    if x < 0.33:
        return "low"
    if x < 0.66:
        return "medium"
    return "high"


# Pricier hurts sentiment (negative tilt); a genuine value gain lifts it; high lock-in
# dampens revolt (a captured cohort grumbles but stays). Internal ordinal tilts only.
_PRICE_TILT = {"cut": 1.0, "flat": 0.0, "hike": -0.6, "steep_hike": -1.0}
_VALUE_TILT = {"worse": -1.0, "same": 0.0, "better": 1.0}
_SWITCH_TILT = {"low": -0.5, "medium": 0.0, "high": 0.4}


PRODUCT_LAUNCH = DomainPack(
    domain_id="product_launch",
    persona_ids=(
        "early_adopter",
        "free_tier_user",
        "power_user",
        "budget_conscious",
        "brand_loyalist",
        "competitor_fan",
        "casual_user",
        "community_voice",
    ),
    # Fade the crowd: loyalists and locked-in power users temper the swing; the rest amplify.
    contra_ids=frozenset({"brand_loyalist", "power_user", "casual_user"}),
    herding={
        "early_adopter": 0.85,
        "free_tier_user": 0.60,
        "power_user": 0.35,
        "budget_conscious": 0.55,
        "brand_loyalist": 0.20,
        "competitor_fan": 0.90,
        "casual_user": 0.30,
        "community_voice": 0.95,
    },
    voice={
        "early_adopter": {
            1: "第一時間升級試新功能,興奮分享上手心得。",
            0: "先看看更新內容,再決定要不要衝。",
            -1: "這版本讓人失望,考慮回退舊版或觀望。",
        },
        "free_tier_user": {
            1: "免費仍夠用,樂見加值,順手推薦朋友。",
            0: "只要免費額度不變,無所謂改版。",
            -1: "怕免費被閹割、逼升級,開始找替代品。",
        },
        "power_user": {
            1: "深度功能有補強,工作流更順,值得。",
            0: "核心功能沒動,維持現狀繼續用。",
            -1: "改動打亂既有工作流,抱怨但短期難搬家。",
        },
        "budget_conscious": {
            1: "同價位變更划算,精打細算後買單。",
            0: "價格沒變就再看看,不急著決定。",
            -1: "漲價超出預算,直接考慮更便宜的方案。",
        },
        "brand_loyalist": {
            1: "支持官方決定,續訂還幫忙護航。",
            0: "相信團隊,照舊使用不動搖。",
            -1: "雖然不滿,但基於信任先留下觀察。",
        },
        "competitor_fan": {
            1: "居然變好了?酸完還是偷偷關注。",
            0: "冷眼旁觀,沒什麼好說的。",
            -1: "抓到把柄大力唱衰,順勢推自家愛牌。",
        },
        "casual_user": {
            1: "剛好有需要就用一下,無特別感覺。",
            0: "沒注意到改版,照習慣用。",
            -1: "變得不好用才會抱怨,否則懶得理。",
        },
        "community_voice": {
            1: "社群風向轉正,發文帶起討論熱度。",
            0: "討論冷清,沒什麼聲量。",
            -1: "論壇一片罵聲,帶頭發起抵制討論。",
        },
    },
    display_name={
        "early_adopter": "嘗鮮玩家",
        "free_tier_user": "免費用戶",
        "power_user": "重度用戶",
        "budget_conscious": "精打細算族",
        "brand_loyalist": "品牌鐵粉",
        "competitor_fan": "競品愛好者",
        "casual_user": "輕度用戶",
        "community_voice": "社群風向",
    },
    axes=(
        Axis(name="price_change", bucket_fn=bucket_price_change, tilt=_PRICE_TILT),
        Axis(name="value_delta", bucket_fn=bucket_value_delta, tilt=_VALUE_TILT),
        Axis(name="switching_cost", bucket_fn=bucket_switching_cost, tilt=_SWITCH_TILT),
    ),
    sensitivity={
        # (price_change, value_delta, switching_cost)
        "early_adopter": (0.2, 1.0, 0.1),
        "free_tier_user": (0.9, 0.4, 0.3),
        "power_user": (0.3, 0.9, 0.7),
        "budget_conscious": (1.0, 0.3, 0.2),
        "brand_loyalist": (0.2, 0.3, 0.6),
        "competitor_fan": (0.4, 0.6, 0.1),
        "casual_user": (0.3, 0.4, 0.5),
        "community_voice": (0.5, 0.7, 0.2),
    },
    consensus_display={
        "negative": "oppose",
        "neutral": "neutral",
        "positive": "support",
    },
    horizon_frame={"intraday": "上線首日", "swing": "數週內", "long": "長期"},
)
