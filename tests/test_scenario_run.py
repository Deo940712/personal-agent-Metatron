"""part-010-slice-001:subprocess adapter + vault 落地 + recall 標記。

Done gate 對應:
- subprocess(runner mock)回真實 JSON → 解析 + 落地 non_authoritative
- crowd-scenario 崩潰 → core 不受影響(ScenarioError,記 event)
- non_authoritative 缺失 → 拒絕落地
- recall 引用 scenario → 帶模擬標記
"""

import json

import pytest

from core import ltm, recall, scenario, stm

T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    return {"db": db, "vault": tmp_path / "vault"}


def _req():
    # software_migration pack 需三軸(breaking_severity/migration_effort/value_gain)
    return scenario.build_request("software_migration", "myproj", "delay_one_week",
                                  {"breaking_severity": "high",
                                   "migration_effort": "heavy",
                                   "value_gain": "low"})


# crowd-scenario CLI 真實輸出結構(pinned commit 實測)
def _real_shape_narrative(non_auth=True, consensus="negative"):
    return {
        "domain": "software_migration", "seed_id": "abc123",
        "artifact_type": "crowd_narrative", "schema_version": "1.0",
        "crowd_consensus": consensus, "consensus_display": "偏空",
        "consensus_mode": "aggregate_neutral",
        "non_authoritative": non_auth, "synthetic_population": True,
        "n_personas": 24, "horizon": "swing", "intensity": "mild",
        "narrator_backend": "deterministic", "narrator_notes": [],
        "narrative_md": "多數 persona 對延後持保留態度。",
        "persona_samples": [
            {"archetype_id": "cautious", "stance": "concern", "excerpt": "延後有風險"},
        ],
    }


# ── subprocess 解析 + 落地 ───────────────────────────────────────────

def test_run_rehearsal_lands_narrative(env):
    runner = lambda req: _real_shape_narrative()
    r = scenario.run_rehearsal(_req(), env["vault"], runner=runner,
                               db=env["db"], ts=T0)
    assert r["non_authoritative"] is True
    assert r["consensus"] == "negative"
    note = ltm.read_note(env["vault"], f"scenarios/{r['note_id']}.md")
    assert note["frontmatter"]["source"] == "scenario_rehearsal"
    assert note["frontmatter"]["non_authoritative"] == "true"
    assert "延後" in note["body"]
    # 事件記錄 completed(標 non-authoritative)
    ev = [e for e in stm.event_query(env["db"], actor="scenario")
          if e["action"] == "completed"]
    assert ev and "non-authoritative" in ev[0]["summary"]


def test_run_rehearsal_subprocess_crash_isolated(env):
    """crowd-scenario 崩潰 → ScenarioError,core(DB/vault)不受影響。"""
    def boom(req):
        raise scenario.ScenarioError("subprocess died")
    with pytest.raises(scenario.ScenarioError):
        scenario.run_rehearsal(_req(), env["vault"], runner=boom, db=env["db"])
    # vault 無殘留、記了 failed event
    scenarios_dir = env["vault"] / "scenarios"
    assert not scenarios_dir.exists() or list(scenarios_dir.glob("*.md")) == []
    failed = [e for e in stm.event_query(env["db"], actor="scenario")
              if e["action"] == "failed"]
    assert failed


def test_run_rehearsal_refuses_non_authoritative(env):
    """crowd-scenario 若沒標 non_authoritative → 拒絕落地(絕不當事實存)。"""
    runner = lambda req: _real_shape_narrative(non_auth=False)
    with pytest.raises(scenario.ScenarioError, match="non_authoritative"):
        scenario.run_rehearsal(_req(), env["vault"], runner=runner, db=env["db"])


def test_run_rehearsal_bad_json_shape(env):
    """runner 回缺 non_authoritative 的 dict → 拒絕。"""
    runner = lambda req: {"crowd_consensus": "x", "narrative_md": "y"}
    with pytest.raises(scenario.ScenarioError):
        scenario.run_rehearsal(_req(), env["vault"], runner=runner, db=env["db"])


# ── recall 標記 ──────────────────────────────────────────────────────

def test_recall_read_note_flags_scenario(env):
    runner = lambda req: _real_shape_narrative()
    r = scenario.run_rehearsal(_req(), env["vault"], runner=runner, db=env["db"], ts=T0)
    out = recall._tool_read_note({"path": f"scenarios/{r['note_id']}.md"}, env["vault"])
    parsed = json.loads(out)
    assert "_non_authoritative_note" in parsed
    assert "模擬演練" in parsed["_non_authoritative_note"]


def test_recall_normal_note_no_flag(env):
    ltm.init_vault(env["vault"])
    ltm.write_note(env["vault"], "semantic", title="真實筆記", body="事實內容",
                   frontmatter={"source": "manual", "tags": ["misc"], "summary": "s"},
                   ts=T0)
    out = recall._tool_read_note({"path": "semantic/20270115-真實筆記.md"}, env["vault"])
    # 路徑可能因 slug 不同;直接讀 registry 找路徑
    path = ltm.registry_entries(env["vault"])[0]["path"]
    parsed = json.loads(recall._tool_read_note({"path": path}, env["vault"]))
    assert "_non_authoritative_note" not in parsed


# ── vendored subprocess 真跑(整合冒煙;非 mock)───────────────────────

def test_vendored_subprocess_smoke(env):
    """真 vendored crowd-scenario subprocess 跑通(確定性、無網路)。"""
    r = scenario.run_rehearsal(_req(), env["vault"], db=env["db"], ts=T0)
    assert r["non_authoritative"] is True
    assert r["consensus"]                            # 有共識值
    assert (env["vault"] / "scenarios" / f"{r['note_id']}.md").exists()
