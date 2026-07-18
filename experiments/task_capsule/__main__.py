"""Task Capsule A/B 實驗 CLI(Todo 13)。

子命令:
  validate   驗證 fixture corpus 與 frozen spec(不跑實驗)
  run        在指定 experiment root 跑 A/B(需明確非正式路徑)
  summarize  從已跑的 experiment root 匯出 evidence 到 output
  dispose    刪除已驗證的 experiment root(只刪帶 marker 者)

安全:所有路徑經 production-path 拒絕;絕不觸碰正式 DB1/vault/transcript。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from experiments.task_capsule import experiment as E
from experiments.task_capsule import fixtures as F
from experiments.task_capsule import metrics as M
from experiments.task_capsule import paths as P


def _cmd_validate(_args: argparse.Namespace) -> int:
    F.validate_corpus(F.load_all())
    spec = M.load_spec()
    print(f"OK: 7 workloads valid; spec_hash={M.spec_hash()[:12]}...; "
          f"threshold={spec['improvement_threshold_pct']}% "
          f"min_qualify={spec['min_qualifying_workloads']} "
          f"p95_budget={spec['p95_budget_pct']}%")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = P.prepare_experiment_root(Path(args.root), resume=args.resume)
    if args.resume:
        summary = E.resume_experiment(root, measured_samples=args.samples)
    else:
        summary = E.run_experiment(root, measured_samples=args.samples)
    print(f"OK: decision={summary['decision']['outcome']} "
          f"qualifying={summary['decision']['qualifying']}/7 "
          f"p95_ok={summary['decision']['p95_ok']}")
    return 0


def _cmd_summarize(args: argparse.Namespace) -> int:
    root = P.assert_safe_experiment_path(Path(args.root))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    E.export_evidence(summary, root, Path(args.out))
    print(f"OK: evidence exported to {args.out}")
    return 0


def _cmd_dispose(args: argparse.Namespace) -> int:
    P.dispose_experiment_root(Path(args.root))
    print(f"OK: disposed {args.root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.task_capsule", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate").set_defaults(func=_cmd_validate)

    p_run = sub.add_parser("run")
    p_run.add_argument("--root", required=True, help="experiment root(非正式路徑)")
    p_run.add_argument("--samples", type=int, default=30)
    p_run.add_argument("--resume", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("--root", required=True)
    p_sum.add_argument("--out", required=True, help="evidence 匯出目錄")
    p_sum.set_defaults(func=_cmd_summarize)

    p_disp = sub.add_parser("dispose")
    p_disp.add_argument("--root", required=True)
    p_disp.set_defaults(func=_cmd_dispose)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
