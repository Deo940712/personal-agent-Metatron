"""Software-migration domain pack — a THIRD domain, neither finance nor consumer product.

This is the clearest proof that the engine is not a "renamed stock-sentiment model": it
rehearses how a software ecosystem reacts to an already-announced **breaking change /
major version rollout**. Same ``DomainPack`` protocol, same firewall — but the personas
are ecosystem cohorts (maintainers, enterprise ops, plugin authors, security teams…), the
axes are migration-specific, and the display vocabulary is ``resist / wait / adopt``.

Scenario: a release has ALREADY been announced. The synthetic crowd rehearses how eight
cohorts react — narrative only, no number, no decision write-back. Inputs are abstract
archetypal snapshots (e.g. ``big_rewrite``), not judgements about any real project.

Three ordinal axes:
- ``breaking_severity`` — how much the release breaks (cosmetic → rewrite).
- ``migration_effort``  — how painful the upgrade is (automated → painful).
- ``value_gain``        — perceived value the new version brings (negligible → game_changing).
"""

from __future__ import annotations

from crowdscenario.domains.base import Axis, DomainPack


def bucket_breaking_severity(x: float) -> str:
    """How much the release breaks, in roughly [0, 1] (bigger = more breaking)."""
    if x < 0.25:
        return "cosmetic"
    if x < 0.5:
        return "minor"
    if x < 0.8:
        return "major"
    return "rewrite"


def bucket_migration_effort(x: float) -> str:
    """How hard the upgrade is, in roughly [0, 1] (bigger = more painful)."""
    if x < 0.25:
        return "automated"
    if x < 0.5:
        return "guided"
    if x < 0.8:
        return "manual"
    return "painful"


def bucket_value_gain(x: float) -> str:
    """Perceived value of the new version, in roughly [0, 1] (bigger = more value)."""
    if x < 0.25:
        return "negligible"
    if x < 0.5:
        return "modest"
    if x < 0.8:
        return "substantial"
    return "game_changing"


# More breaking / more painful hurts sentiment (negative tilt); more value lifts it.
# Internal ordinal tilts only — they never leave the engine.
_SEVERITY_TILT = {"cosmetic": 0.3, "minor": 0.0, "major": -0.6, "rewrite": -1.0}
_EFFORT_TILT = {"automated": 0.4, "guided": 0.0, "manual": -0.5, "painful": -1.0}
_VALUE_TILT = {"negligible": -0.6, "modest": 0.0, "substantial": 0.7, "game_changing": 1.0}


SOFTWARE_MIGRATION = DomainPack(
    domain_id="software_migration",
    persona_ids=(
        "early_adopter",
        "oss_maintainer",
        "enterprise_ops",
        "plugin_ecosystem",
        "security_team",
        "hobby_user",
        "tech_influencer",
        "conservative_team",
    ),
    # Fade the hype: the slow, risk-averse cohorts temper the swing; the rest amplify it.
    contra_ids=frozenset({"enterprise_ops", "conservative_team", "security_team"}),
    herding={
        "early_adopter": 0.85,
        "oss_maintainer": 0.30,
        "enterprise_ops": 0.15,
        "plugin_ecosystem": 0.45,
        "security_team": 0.25,
        "hobby_user": 0.70,
        "tech_influencer": 0.95,
        "conservative_team": 0.20,
    },
    voice={
        "early_adopter": {
            1: "第一時間升上新版,興奮試玩新特性、發推分享。",
            0: "先看看 release note,再決定要不要衝。",
            -1: "改動太大又沒亮點,暫時留在舊版觀望。",
        },
        "oss_maintainer": {
            1: "破壞可控、遷移有工具,盡快跟上並更新下游套件。",
            0: "先評估 breaking 影響面,排進下個維護週期。",
            -1: "breaking 太狠,下游全要改,先釘住舊版擋著。",
        },
        "enterprise_ops": {
            1: "遷移成本低又有支援,排入變更視窗分批升。",
            0: "等 patch 版穩定、看社群踩雷再說,先不動。",
            -1: "遷移成本高、風險大,凍結版本、走 LTS 保平安。",
        },
        "plugin_ecosystem": {
            1: "API 更好用,重寫外掛值得,順勢推新版。",
            0: "等核心 API 定稿,再決定外掛怎麼改。",
            -1: "API 又斷了,外掛全爆,發文抱怨相容性。",
        },
        "security_team": {
            1: "舊版快 EOL,新版修了洞,推動盡早升級。",
            0: "先審新版的支援期與 CVE 紀錄,再給建議。",
            -1: "新版太新、風險未明,先留舊版等它成熟。",
        },
        "hobby_user": {
            1: "文件清楚就跟著升,順便學新東西。",
            0: "沒空細看,等有人寫好教學再動。",
            -1: "升級搞半天又踩雷,乾脆先不升。",
        },
        "tech_influencer": {
            1: "帶起風向大推新版,直播開箱衝聲量。",
            0: "先觀望討論熱度,再決定要不要做內容。",
            -1: "帶頭唱衰這次改版,發長文列一堆坑。",
        },
        "conservative_team": {
            1: "難得穩又有價值,破例排一次升級。",
            0: "照舊用穩定版,不追新、不當白老鼠。",
            -1: "越多人衝我越不動,等塵埃落定再說。",
        },
    },
    display_name={
        "early_adopter": "嘗鮮開發者",
        "oss_maintainer": "下游套件維護者",
        "enterprise_ops": "企業運維",
        "plugin_ecosystem": "外掛生態作者",
        "security_team": "資安團隊",
        "hobby_user": "業餘使用者",
        "tech_influencer": "技術風向 KOL",
        "conservative_team": "保守團隊（LTS 派）",
    },
    axes=(
        Axis(name="breaking_severity", bucket_fn=bucket_breaking_severity, tilt=_SEVERITY_TILT),
        Axis(name="migration_effort", bucket_fn=bucket_migration_effort, tilt=_EFFORT_TILT),
        Axis(name="value_gain", bucket_fn=bucket_value_gain, tilt=_VALUE_TILT),
    ),
    sensitivity={
        # (breaking_severity, migration_effort, value_gain)
        "early_adopter": (0.2, 0.2, 1.0),
        "oss_maintainer": (1.0, 0.7, 0.3),
        "enterprise_ops": (0.6, 1.0, 0.3),
        "plugin_ecosystem": (0.9, 0.5, 0.5),
        "security_team": (0.5, 0.3, 0.6),
        "hobby_user": (0.3, 0.6, 0.4),
        "tech_influencer": (0.4, 0.2, 0.8),
        "conservative_team": (0.7, 0.6, 0.4),
    },
    consensus_display={
        "negative": "resist",
        "neutral": "wait",
        "positive": "adopt",
    },
    horizon_frame={"intraday": "公告當週", "swing": "一個發佈週期", "long": "LTS 週期"},
    # Demonstration variants for the two loudest, most emotion-amplifying cohorts.
    voice_variants={
        "tech_influencer": {
            1: (
                "帶起風向大推新版,直播開箱衝聲量。",
                "發長文吹爆新版,留言區一片跟風想升。",
                "剪了支上手影片帶節奏,大家都在問怎麼裝。",
            ),
            -1: (
                "帶頭唱衰這次改版,發長文列一堆坑。",
                "開嗆這版根本沒準備好,勸大家先別碰。",
                "拍了支踩雷實錄,底下一堆人附和別升。",
            ),
        },
        "hobby_user": {
            1: (
                "文件清楚就跟著升,順便學新東西。",
                "看到教學就照做升上去了,還算順。",
                "跟著社群步驟升級,沒踩到什麼雷。",
            ),
            -1: (
                "升級搞半天又踩雷,乾脆先不升。",
                "照教學還是失敗,回退舊版先用著。",
                "環境弄壞了修不好,決定等穩定再說。",
            ),
        },
    },
)
