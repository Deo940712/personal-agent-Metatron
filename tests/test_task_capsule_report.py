"""part-003.2-slice-001 Todo 2/14:ECC 報告 deterministic checker。

CheckTaskCapsuleExperiment.py 有 --phase pre-result|final。
pre-result:允許 result/recommendation placeholder;需含全部 section、八個 ECC
source URL、關鍵 phrase(ECC 是證據非權威 / 非 semantic RAG / 無自主 paging)。
final:不允許 placeholder;交叉核對 evidence 路徑;無 B/C/D 採用聲明。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / ".beacon" / "verification" / "CheckTaskCapsuleExperiment.py"
REPORT = ROOT / "docs" / "ECC-TASK-CAPSULE-REPORT-zh.md"


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True, text=True, cwd=str(ROOT))


# ── checker 存在且可執行 ──────────────────────────────────────────────

def test_checker_exists():
    assert CHECKER.exists()


def test_report_exists():
    assert REPORT.exists()


# ── pre-result phase:報告當前狀態應通過 ──────────────────────────────

def test_pre_result_phase_passes():
    r = _run("--report", str(REPORT), "--phase", "pre-result")
    assert r.returncode == 0, r.stdout + r.stderr


# ── checker 抓缺漏 ───────────────────────────────────────────────────

def test_checker_rejects_missing_source(tmp_path):
    # 造一份缺 ECC source 的報告 → 拒絕
    bad = tmp_path / "bad.md"
    bad.write_text("# 報告\n\n沒有任何 ECC 來源連結。\n", encoding="utf-8")
    r = _run("--report", str(bad), "--phase", "pre-result")
    assert r.returncode != 0


def test_checker_rejects_missing_key_phrase(tmp_path):
    bad = tmp_path / "bad2.md"
    # 有 URL 但缺關鍵 phrase
    bad.write_text(
        "# 報告\n"
        "https://github.com/affaan-m/ECC/blob/main/scripts/lib/state-store/migrations.js\n",
        encoding="utf-8")
    r = _run("--report", str(bad), "--phase", "pre-result")
    assert r.returncode != 0


# ── final phase:定稿報告(無 placeholder、引用 evidence)應通過 ─────────

def test_final_phase_passes_on_finalized_report():
    r = _run("--report", str(REPORT), "--phase", "final")
    assert r.returncode == 0, r.stdout + r.stderr


def test_final_phase_rejects_unresolved_placeholder(tmp_path):
    # 帶 RESULT_PLACEHOLDER 的報告在 final 應被拒
    text = REPORT.read_text(encoding="utf-8")
    text = text.replace("## 實驗結果\n", "## 實驗結果\n<!-- RESULT_PLACEHOLDER -->\n")
    bad = tmp_path / "with_placeholder.md"
    bad.write_text(text, encoding="utf-8")
    r = _run("--report", str(bad), "--phase", "final")
    assert r.returncode != 0


def test_final_phase_rejects_adoption_claim(tmp_path):
    text = REPORT.read_text(encoding="utf-8") + "\n\n本專案已採用 B。\n"
    bad = tmp_path / "adopts.md"
    bad.write_text(text, encoding="utf-8")
    r = _run("--report", str(bad), "--phase", "final")
    assert r.returncode != 0
