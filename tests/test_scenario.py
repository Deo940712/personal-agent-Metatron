"""part-010-slice-000:scenarios 專區 + bucket firewall + seed 建構。

Done gate 對應:
- bucketize 邊界/確定性
- build_request 拒 raw number（firewall）
- store_narrative 標 non_authoritative + 不進 semantic
"""

from pathlib import Path

import pytest

from core import ltm, scenario, stm

T0 = 1_800_000_000

INF = float("inf")
SLEEP_THRESHOLDS = [(5, "severely_low"), (7, "low"), (9, "normal"), (INF, "high")]


@pytest.fixture()
def vault(tmp_path):
    return tmp_path / "vault"


# ── bucketize ────────────────────────────────────────────────────────

def test_bucketize_boundaries():
    assert scenario.bucketize(4.7, SLEEP_THRESHOLDS) == "severely_low"
    assert scenario.bucketize(5.0, SLEEP_THRESHOLDS) == "severely_low"  # ≤ 上界
    assert scenario.bucketize(6.0, SLEEP_THRESHOLDS) == "low"
    assert scenario.bucketize(8.5, SLEEP_THRESHOLDS) == "normal"
    assert scenario.bucketize(12, SLEEP_THRESHOLDS) == "high"


def test_bucketize_deterministic():
    assert scenario.bucketize(6.3, SLEEP_THRESHOLDS) == \
        scenario.bucketize(6.3, SLEEP_THRESHOLDS)


def test_bucketize_rejects_non_number():
    with pytest.raises(scenario.ScenarioError):
        scenario.bucketize("4.7", SLEEP_THRESHOLDS)
    with pytest.raises(scenario.ScenarioError):
        scenario.bucketize(True, SLEEP_THRESHOLDS)


def test_ordinal_axis_mapping():
    assert scenario.ordinal_axis("severely_low") == 0.05
    assert scenario.ordinal_axis("overloaded") == 0.95
    assert scenario.ordinal_axis("unknown_label") == 0.5      # 中點 fallback
    assert 0.0 <= scenario.ordinal_axis("normal") <= 1.0


# ── build_request（firewall：拒 raw number）─────────────────────────

def test_build_request_from_buckets():
    req = scenario.build_request(
        "software_migration", "myproj", "delay_one_week",
        {"breaking_severity": "high", "migration_effort": "heavy"})
    assert req.domain == "software_migration"
    assert req.metrics["breaking_severity"] == 0.75
    assert req.metrics["migration_effort"] == 0.8
    # 溯源 buckets 保留
    assert req.buckets["breaking_severity"] == "high"
    # 不含任何原始數字——metrics 全在 [0,1]
    assert all(0.0 <= v <= 1.0 for v in req.metrics.values())


def test_build_request_rejects_raw_number():
    """firewall 硬規則:metrics 只能吃 ordinal bucket 標籤,不能吃 raw number。"""
    with pytest.raises(scenario.ScenarioError, match="raw numbers must be bucketized"):
        scenario.build_request("software_migration", "p", "s",
                               {"breaking_severity": 0.95})   # raw float


def test_build_request_validates_fields():
    with pytest.raises(scenario.ScenarioError):
        scenario.build_request("", "p", "s", {"a": "high"})
    with pytest.raises(scenario.ScenarioError):
        scenario.build_request("d", "p", "s", {})             # 空 metrics


# ── store_narrative（non_authoritative + 不進 semantic）──────────────

def _narrative(non_auth=True):
    return {
        "non_authoritative": non_auth,
        "synthetic_population": True,
        "crowd_consensus": "hold",
        "narrative_md": "多數 persona 傾向維持現狀。",
        "persona_samples": [
            {"archetype_id": "cautious", "stance": "hold", "excerpt": "先觀望"},
        ],
    }


def test_store_narrative_lands_in_scenarios(vault):
    req = scenario.build_request("software_migration", "myproj", "delay",
                                 {"breaking_severity": "high"})
    note_id = scenario.store_narrative(vault, req, _narrative(), ts=T0)
    # 存在 vault/scenarios/,不在 semantic/
    assert (vault / "scenarios" / f"{note_id}.md").exists()
    semantic = list((vault / "semantic").glob("*.md")) if (vault / "semantic").exists() else []
    assert semantic == []
    note = ltm.read_note(vault, f"scenarios/{note_id}.md")
    assert note["frontmatter"]["source"] == "scenario_rehearsal"
    assert note["frontmatter"]["non_authoritative"] == "true"
    assert "模擬演練" in note["body"]


def test_store_refuses_non_flagged_narrative(vault):
    """crowd-scenario 輸出必須標 non_authoritative;缺失/false → 拒絕落地。"""
    req = scenario.build_request("software_migration", "p", "s",
                                 {"breaking_severity": "high"})
    with pytest.raises(scenario.ScenarioError, match="non_authoritative"):
        scenario.store_narrative(vault, req, _narrative(non_auth=False), ts=T0)
    with pytest.raises(scenario.ScenarioError):
        scenario.store_narrative(vault, req, {"crowd_consensus": "x"}, ts=T0)


def test_store_registers_but_marks_synthetic(vault):
    req = scenario.build_request("product_launch", "habit", "sleep_early",
                                 {"value_delta": "high"})
    scenario.store_narrative(vault, req, _narrative(), ts=T0)
    reg = ltm.registry_entries(vault)
    hit = [e for e in reg if e["path"].startswith("scenarios/")]
    assert len(hit) == 1
    assert "模擬演練" in hit[0]["summary"]


def test_scenarios_subdir_allowed(vault):
    ltm.init_vault(vault)
    assert (vault / "scenarios").exists()
    assert "scenarios" in ltm.ALLOWED_SUBDIRS
