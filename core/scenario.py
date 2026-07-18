"""情境演練 adapter(part-010;ARCHITECTURE §15 Scenario Rehearsal)。

用 vendored crowd-scenario 引擎把已決定的情境交給合成 persona 演練,產**非權威**
敘事報告。slice-000 只做確定性基座:

- bucket 化 firewall:raw 數字 → ordinal(0-1 軸值);**原始數字永不跨越 firewall**
- ScenarioRequest:只收 bucket 化後的軸值,拒 raw number
- store_narrative:報告存 vault/scenarios/ 專區,硬標 non_authoritative——
  不進 semantic 事實層、不進 Personal Model facet 證據

crowd-scenario 契約(contracts.py)本身也硬拒 raw number 進 seed、輸出硬標
non_authoritative;Metatron 這端做雙重保險(bucket 化 + 標記存放)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import config
from core import stm


class ScenarioError(ValueError):
    """情境請求/落地層級的驗證失敗(firewall 違規等)。"""


def bucketize(value: float, thresholds: list[tuple[float, str]]) -> str:
    """raw 數字 → ordinal bucket 標籤(確定性 firewall)。

    thresholds:遞增的 (上界, 標籤) 清單;value ≤ 上界 → 該標籤。超過最後上界 →
    最後一個標籤(呼叫端保證最後上界為 +inf 或足夠大)。
    例:bucketize(4.7, [(5, "severely_low"), (7, "low"), (9, "normal"),
                        (float("inf"), "high")]) == "severely_low"
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"bucketize value must be a number, got {type(value).__name__}")
    for upper, label in thresholds:
        if value <= upper:
            return label
    return thresholds[-1][1]


# bucket 標籤 → 0-1 軸值(crowd-scenario --metrics 只吃 0-1;ordinal 映射,非原始值)
_ORDINAL_TO_AXIS = {
    "severely_low": 0.05, "low": 0.25, "below_normal": 0.35,
    "normal": 0.5, "above_normal": 0.65, "high": 0.75,
    "severe": 0.9, "extreme": 0.95,
    "none": 0.0, "some": 0.4, "heavy": 0.8, "overloaded": 0.95,
}


def ordinal_axis(bucket: str) -> float:
    """ordinal bucket 標籤 → 0-1 軸值(給 crowd-scenario)。未知標籤 → 中點 0.5。"""
    return _ORDINAL_TO_AXIS.get(bucket, 0.5)


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    """一次演練請求。metrics 只收 bucket 化後的 0-1 軸值——**拒絕 raw number**。"""

    domain: str                       # crowd-scenario pack id(既有 pack)
    symbol: str                       # 演練標的代號(去識別化)
    scenario: str                     # 情境標籤
    metrics: dict[str, float]         # 軸名 → 0-1 值(bucket 化來的)
    buckets: dict[str, str] = field(default_factory=dict)  # 軸名 → ordinal 標籤(溯源)
    n: int = 30


def build_request(domain: str, symbol: str, scenario: str,
                  axis_buckets: dict[str, str], *, n: int = 30) -> ScenarioRequest:
    """由 (軸名 → ordinal bucket) 組 ScenarioRequest。

    firewall:輸入是 ordinal 標籤(非 raw number),轉成 0-1 軸值。任何值超出
    [0,1] 或非 bucket 來源 → ScenarioError。
    """
    if not isinstance(domain, str) or not domain.strip():
        raise ScenarioError("domain must be a non-empty string")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ScenarioError("symbol must be a non-empty string")
    if not isinstance(scenario, str) or not scenario.strip():
        raise ScenarioError("scenario must be a non-empty string")
    if not axis_buckets:
        raise ScenarioError("axis_buckets must be non-empty")
    metrics: dict[str, float] = {}
    for axis, bucket in axis_buckets.items():
        if not isinstance(bucket, str):
            raise ScenarioError(
                f"axis {axis!r} value must be an ordinal bucket label (str), "
                f"got {type(bucket).__name__} — raw numbers must be bucketized first")
        val = ordinal_axis(bucket)
        if not 0.0 <= val <= 1.0:
            raise ScenarioError(f"axis {axis!r} value out of [0,1]: {val}")
        metrics[axis] = val
    return ScenarioRequest(domain=domain.strip(), symbol=symbol.strip(),
                           scenario=scenario.strip(), metrics=metrics,
                           buckets=dict(axis_buckets), n=n)


def store_narrative(vault: Path, request: ScenarioRequest, narrative: dict, *,
                    ts: int | None = None) -> str:
    """把演練報告存 vault/scenarios/ 專區,硬標 non_authoritative。

    - 必須 narrative['non_authoritative'] 為真(crowd-scenario 保證;缺失 → 拒絕)。
    - frontmatter:source=scenario_rehearsal / non_authoritative=true /
      synthetic_population=true / 溯源 buckets。**不進 semantic、不進 facet**。
    回 note_id。
    """
    from core import ltm

    if not _truthy(narrative.get("non_authoritative")):
        raise ScenarioError(
            "refuse to store: narrative is not marked non_authoritative "
            "(scenario output must never be treated as fact)")
    ltm.init_vault(vault)
    when = ts if ts is not None else stm.now()
    consensus = str(narrative.get("crowd_consensus", "unknown"))
    body_lines = [
        "> ⚠️ 這是**模擬演練**產物,非事實、非預測。合成 persona 群體反應,",
        "> 僅供決策前參考,不得當作真實資料或未來預測。",
        "",
        f"**情境**:{request.scenario}（domain={request.domain}, symbol={request.symbol}）",
        f"**群體共識**:{consensus}",
        "",
        str(narrative.get("narrative_md", "")).strip(),
    ]
    samples = narrative.get("persona_samples") or []
    if samples:
        body_lines.append("\n## Persona 樣本")
        for s in samples:
            body_lines.append(f"- [{s.get('archetype_id', '?')}/{s.get('stance', '?')}] "
                              f"{s.get('excerpt', '')}")
    frontmatter = {
        "source": "scenario_rehearsal",
        "non_authoritative": True,
        "synthetic_population": True,
        "domain": request.domain,
        "scenario": request.scenario,
        "crowd_consensus": consensus,
        "buckets": [f"{k}={v}" for k, v in request.buckets.items()],
        "rehearsed_at": datetime.fromtimestamp(when).strftime("%Y-%m-%d %H:%M"),
        "tags": ["scenario"],
        "summary": f"[模擬演練] {request.scenario} → {consensus}",
    }
    return ltm.write_note(vault, "scenarios",
                          title=f"演練:{request.scenario}",
                          body="\n".join(body_lines),
                          frontmatter=frontmatter, ts=when)


def _truthy(v) -> bool:
    return str(v).lower() in ("true", "1", "yes")


# ── subprocess 演練(part-010-slice-001;vendored crowd-scenario 黑箱)──────

def _subprocess_runner(request: ScenarioRequest) -> dict:
    """預設 runner:subprocess 呼叫 vendored crowd-scenario CLI → 解析 JSON。

    PYTHONPATH 指向 vendored src;crowd-scenario 確定性、無網路、firewall 自帶。
    subprocess 隔離:它崩潰/漂移不影響 core。失敗 → ScenarioError(呼叫端容錯)。
    """
    import json
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (f"{config.CROWD_SCENARIO_SRC}{os.pathsep}{existing}"
                         if existing else str(config.CROWD_SCENARIO_SRC))
    cmd = [sys.executable, "-m", "crowdscenario", "run",
           "--domain", request.domain, "--symbol", request.symbol,
           "--scenario", request.scenario, "--n", str(request.n),
           "--metrics", json.dumps(request.metrics)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=60, check=True)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ScenarioError(f"crowd-scenario subprocess failed: {exc}") from exc
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ScenarioError(
            f"crowd-scenario returned non-JSON: {proc.stdout[:200]!r}") from exc


def run_rehearsal(request: ScenarioRequest, vault: Path, *,
                  runner=None, db: Path | None = None,
                  ts: int | None = None) -> dict:
    """執行一次演練 → 存 vault/scenarios/。回 {note_id, consensus, non_authoritative}。

    runner 注入(預設 subprocess;測試 mock)。crowd-scenario 崩潰 → ScenarioError,
    但記 event 後由呼叫端決定;non_authoritative 缺失 → store_narrative 拒絕落地。
    """
    run = runner or _subprocess_runner
    try:
        narrative = run(request)
    except ScenarioError as exc:
        stm.event_append(db, "scenario", "failed",
                         f"rehearsal failed for {request.scenario}: {exc}")
        raise
    note_id = store_narrative(vault, request, narrative, ts=ts)
    stm.event_append(db, "scenario", "completed",
                     f"rehearsed {request.scenario} (domain={request.domain}) "
                     f"→ {narrative.get('crowd_consensus', '?')} [non-authoritative]",
                     target=f"scenarios/{note_id}")
    return {"note_id": note_id,
            "consensus": narrative.get("crowd_consensus"),
            "non_authoritative": _truthy(narrative.get("non_authoritative"))}


# ── 個人 scenario templates(part-010-slice-002)──────────────────────────
# crowd-scenario `--domain` 只接受內建 3 packs 且不改 vendored;個人情境映射到
# 最貼近的既有 pack + bucket 化的軸值。讀 Metatron 狀態 → firewall bucket → request。

_COUNT_THRESHOLDS = [(0, "none"), (3, "some"), (8, "heavy"), (float("inf"), "overloaded")]


def _template_personal_schedule(db: Path | None, now_ts: int) -> ScenarioRequest:
    """排程壓力演練 → software_migration pack。

    軸映射:待辦量 → breaking_severity(壓力大小);逾期量 → migration_effort
    (處理痛苦度);近期行程密度 → value_gain(逆:越密回報越低)。全 bucket 化。
    """
    pending = [t for t in stm.task_list(db)
               if t["status"] in ("pending", "in_progress", "waiting_user")]
    overdue = [t for t in pending
               if t.get("due_at") and t["due_at"] < now_ts]
    upcoming = _count_upcoming_schedule(db, now_ts, days=3)
    return build_request(
        "software_migration", "my-schedule", "next_week_load",
        {"breaking_severity": bucketize(len(pending), _COUNT_THRESHOLDS),
         "migration_effort": bucketize(len(overdue), _COUNT_THRESHOLDS),
         "value_gain": _invert(bucketize(upcoming, _COUNT_THRESHOLDS))},
        n=config.SCENARIO_DEFAULT_N)


def _template_habit_change(db: Path | None, now_ts: int) -> ScenarioRequest:
    """習慣改變演練 → product_launch pack。

    軸映射:現有 routine 穩定度 → switching_cost(慣性);goal 數 → value_delta
    (期望效益);待辦壓力 → price_change(改變成本)。
    """
    routine = stm.facet_get_active(db, "routine", "active_bucket")
    goals = stm.facet_list(db, facet_class="goal")
    pending = [t for t in stm.task_list(db)
               if t["status"] in ("pending", "in_progress", "waiting_user")]
    switching = "high" if (routine and routine["state"] == "stable") else "some"
    return build_request(
        "product_launch", "my-habit", "change_routine",
        {"switching_cost": switching,
         "value_delta": bucketize(len(goals), _COUNT_THRESHOLDS),
         "price_change": bucketize(len(pending), _COUNT_THRESHOLDS)},
        n=config.SCENARIO_DEFAULT_N)


def _template_project_portfolio(db: Path | None, now_ts: int) -> ScenarioRequest:
    """專案取捨演練 → software_migration pack。

    軸映射:專案數 → breaking_severity;有 blockers 的專案數 → migration_effort;
    活躍專案 → value_gain。
    """
    projects = stm.project_show(db)
    blocked = [p for p in projects if p.get("blockers")]
    active = [p for p in projects if p.get("next_action")]
    return build_request(
        "software_migration", "my-portfolio", "defer_side_project",
        {"breaking_severity": bucketize(len(projects), _COUNT_THRESHOLDS),
         "migration_effort": bucketize(len(blocked), _COUNT_THRESHOLDS),
         "value_gain": bucketize(len(active), _COUNT_THRESHOLDS)},
        n=config.SCENARIO_DEFAULT_N)


TEMPLATES = {
    "personal_schedule": _template_personal_schedule,
    "habit_change": _template_habit_change,
    "project_portfolio": _template_project_portfolio,
}


def _invert(bucket: str) -> str:
    """count bucket 反轉(none↔overloaded);給「越多越差」的軸。"""
    order = ["none", "some", "heavy", "overloaded"]
    return order[len(order) - 1 - order.index(bucket)] if bucket in order else bucket


def _count_upcoming_schedule(db: Path | None, now_ts: int, days: int) -> int:
    con = stm.connect(db)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM schedule WHERE status='active' "
            "AND start_at BETWEEN ? AND ?",
            (now_ts, now_ts + days * 86400)).fetchone()[0]
    finally:
        con.close()


def rehearse_template(template: str, db: Path | None, vault: Path, *,
                      runner=None, now_ts: int | None = None) -> dict:
    """由 template 名讀 Metatron 狀態 → build_request → run_rehearsal。

    純使用者觸發(CLI);advisor 自動觸發列後續。未知 template → ScenarioError。
    """
    builder = TEMPLATES.get(template)
    if builder is None:
        raise ScenarioError(f"unknown template: {template!r} "
                            f"(available: {sorted(TEMPLATES)})")
    now = now_ts if now_ts is not None else stm.now()
    request = builder(db, now)
    return run_rehearsal(request, vault, runner=runner, db=db, ts=now)


def main(argv: list[str] | None = None) -> int:
    """CLI:python -m core.scenario rehearse <template>。"""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m core.scenario",
                                     description="情境演練(非權威模擬)")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("rehearse", help="用 Metatron 狀態跑一次演練")
    r.add_argument("template", choices=sorted(TEMPLATES))
    r.add_argument("--db", type=Path, default=None)
    r.add_argument("--vault", type=Path, default=None)
    args = parser.parse_args(argv)

    vault = args.vault or config.VAULT_PATH
    try:
        result = rehearse_template(args.template, args.db, vault)
    except ScenarioError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"OK: [模擬演練·非事實] {args.template} → {result['consensus']} "
          f"(vault/scenarios/{result['note_id']})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
