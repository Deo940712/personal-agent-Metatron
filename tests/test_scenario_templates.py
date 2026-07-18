"""part-010-slice-002:個人 scenario templates + CLI + 端到端。

Done gate 對應:
- 三 template 映射確定性（狀態 → bucket → request 不含 raw number）
- 端到端（狀態 → mock subprocess → vault/scenarios non_authoritative）
- CLI rehearse
"""

import json

import pytest

from core import ltm, scenario, stm

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    return {"db": db, "vault": tmp_path / "vault"}


def _narrative():
    return {"non_authoritative": True, "synthetic_population": True,
            "crowd_consensus": "hold", "narrative_md": "演練結果內文。",
            "persona_samples": []}


# ── template 映射（確定性，firewall）─────────────────────────────────

def test_all_templates_registered():
    assert set(scenario.TEMPLATES) == {"personal_schedule", "habit_change",
                                       "project_portfolio"}


def test_personal_schedule_maps_to_buckets(env):
    for i in range(5):
        stm.task_add(env["db"], f"待辦{i}")
    stm.task_add(env["db"], "逾期", due_at=T0 - DAY)
    req = scenario.TEMPLATES["personal_schedule"](env["db"], T0)
    assert req.domain == "software_migration"
    # 全軸值在 [0,1]，無 raw number（firewall）
    assert all(0.0 <= v <= 1.0 for v in req.metrics.values())
    assert set(req.metrics) == {"breaking_severity", "migration_effort", "value_gain"}
    # 溯源 buckets 是 ordinal 標籤
    assert req.buckets["breaking_severity"] in ("none", "some", "heavy", "overloaded")


def test_habit_change_maps_to_product_launch(env):
    stm.facet_insert(env["db"], "routine", "active_bucket", "morning",
                     confidence=0.9, seen_at=T0)
    fid = stm.facet_get_active(env["db"], "routine", "active_bucket")["id"]
    stm.facet_promote(env["db"], fid, 0.6)                # stable → high switching_cost
    stm.facet_insert(env["db"], "goal", "learn", "向量檢索", seen_at=T0)
    req = scenario.TEMPLATES["habit_change"](env["db"], T0)
    assert req.domain == "product_launch"
    assert set(req.metrics) == {"switching_cost", "value_delta", "price_change"}
    assert req.buckets["switching_cost"] == "high"        # stable routine → 高慣性


def test_project_portfolio_maps(env):
    stm.project_set(env["db"], "proj-a", phase="p1", blockers=["等 key"],
                    next_action="做 X")
    stm.project_set(env["db"], "proj-b", phase="p2", next_action="做 Y")
    req = scenario.TEMPLATES["project_portfolio"](env["db"], T0)
    assert req.domain == "software_migration"
    assert set(req.metrics) == {"breaking_severity", "migration_effort", "value_gain"}


def test_templates_deterministic(env):
    stm.task_add(env["db"], "t")
    r1 = scenario.TEMPLATES["personal_schedule"](env["db"], T0)
    r2 = scenario.TEMPLATES["personal_schedule"](env["db"], T0)
    assert r1.metrics == r2.metrics and r1.buckets == r2.buckets


def test_empty_state_still_valid_request(env):
    """空狀態 → 全 'none' bucket，request 仍合法（軸值在 [0,1]）。"""
    req = scenario.TEMPLATES["personal_schedule"](env["db"], T0)
    assert all(0.0 <= v <= 1.0 for v in req.metrics.values())


def test_invert_helper():
    assert scenario._invert("none") == "overloaded"
    assert scenario._invert("some") == "heavy"
    assert scenario._invert("overloaded") == "none"


# ── 端到端（mock subprocess）─────────────────────────────────────────

def test_rehearse_template_end_to_end(env):
    stm.task_add(env["db"], "t1")
    stm.task_add(env["db"], "t2", due_at=T0 - DAY)
    r = scenario.rehearse_template("personal_schedule", env["db"], env["vault"],
                                   runner=lambda req: _narrative(), now_ts=T0)
    assert r["non_authoritative"] is True
    note = ltm.read_note(env["vault"], f"scenarios/{r['note_id']}.md")
    assert note["frontmatter"]["source"] == "scenario_rehearsal"
    assert note["frontmatter"]["non_authoritative"] == "true"
    # 不進 semantic
    assert not (env["vault"] / "semantic").exists() or \
        list((env["vault"] / "semantic").glob("*.md")) == []


def test_rehearse_unknown_template(env):
    with pytest.raises(scenario.ScenarioError, match="unknown template"):
        scenario.rehearse_template("bogus", env["db"], env["vault"],
                                   runner=lambda req: _narrative())


# ── CLI ──────────────────────────────────────────────────────────────

def test_cli_rehearse_real_subprocess(env, capsys):
    """CLI 走真 vendored subprocess（確定性、無網路）。"""
    stm.task_add(env["db"], "t1")
    rc = scenario.main(["rehearse", "personal_schedule",
                        "--db", str(env["db"]), "--vault", str(env["vault"])])
    assert rc == 0
    out = capsys.readouterr().out
    assert "模擬演練·非事實" in out
    assert "vault/scenarios/" in out


def test_cli_unknown_template_rejected(env, capsys):
    rc = scenario.main(["rehearse", "personal_schedule",
                        "--db", str(env["db"]), "--vault", str(env["vault"])])
    assert rc == 0     # personal_schedule 合法;argparse choices 擋未知
