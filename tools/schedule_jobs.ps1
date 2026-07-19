# ─── MY AGENT 排程註冊(Windows Task Scheduler)───────────────────────
# How to run(以一般使用者身分即可):
#   powershell -ExecutionPolicy Bypass -File tools\schedule_jobs.ps1            # 註冊全部
#   powershell -ExecutionPolicy Bypass -File tools\schedule_jobs.ps1 -Remove    # 移除全部
#
# 設計:
# - idempotent:重跑會先移除同名 task 再註冊(安全)。
# - 每個 job 獨立 task;一個壞不影響其他(agent_runs 記每次 status)。
# - 無 LLM key 時:remind/scout 照常;consolidate/curate/advise/track 會
#   fail-closed 記 error 於 agent_runs——設好 MY_AGENT_LLM_API_KEY(User 環境變數)
#   後自動恢復,不需重新註冊。
# - stdout/stderr 附加到 DATA_DIR\logs\<job>.log(輪替由使用者手動;個人量級可接受)。

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $PSScriptRoot          # tools/ 的上一層 = repo 根
$Python  = "C:\Users\tcart\anaconda3\python.exe"
$LogDir  = "C:\Users\tcart\my-agent-data\logs"
$TaskPrefix = "MyAgent"

# job 名 → (排程觸發, 說明)
$Jobs = @(
    @{ Name = "remind";      Trigger = "minute"; Interval = 15; Desc = "到期提醒(確定性,無 LLM)" },
    @{ Name = "consolidate"; Trigger = "daily";  At = "03:00";  Desc = "夜間記憶蒸餾(需 LLM key)" },
    @{ Name = "curate";      Trigger = "daily";  At = "03:30";  Desc = "inbox 評分入庫(需 LLM key)" },
    @{ Name = "track";       Trigger = "daily";  At = "04:00";  Desc = "專案三源掃描(需 LLM key)" },
    @{ Name = "scout";       Trigger = "daily";  At = "05:00";  Desc = "知識偵察抓取(確定性,無 LLM)" },
    @{ Name = "advise";      Trigger = "daily";  At = "08:00";  Desc = "晨間主動建議(quiet 零 LLM;reflect 需 key)" }
)

function Remove-Jobs {
    foreach ($j in $Jobs) {
        $name = "$TaskPrefix-$($j.Name)"
        # 首次執行 task 不存在是預期情況;cmd /c 吞 stderr 避免 EA=Stop 中止
        cmd /c "schtasks /Delete /TN $name /F >nul 2>&1"
        Write-Host "removed (if existed): $name"
    }
    cmd /c "schtasks /Delete /TN $TaskPrefix-dashboard /F >nul 2>&1"   # part-014
    Write-Host "removed (if existed): $TaskPrefix-dashboard"
}

if ($Remove) { Remove-Jobs; exit 0 }

New-Item -ItemType Directory -Force $LogDir | Out-Null
Remove-Jobs 2>$null   # idempotent:先清同名

$Runner = Join-Path $PSScriptRoot "run_job.cmd"   # workdir/log 都在 runner 內處理
foreach ($j in $Jobs) {
    $name = "$TaskPrefix-$($j.Name)"
    # 路徑含空白(MY AGENT):/TR 值需內嵌引號;經 cmd /c 傳遞用 \" 逸出
    $tr = '\"' + $Runner + '\" ' + $j.Name
    if ($j.Trigger -eq "minute") {
        cmd /c "schtasks /Create /TN $name /TR `"$tr`" /SC MINUTE /MO $($j.Interval) /F >nul"
    } else {
        cmd /c "schtasks /Create /TN $name /TR `"$tr`" /SC DAILY /ST $($j.At) /F >nul"
    }
    if ($LASTEXITCODE -ne 0) { throw "failed to register $name" }
    Write-Host "registered: $name ($($j.Desc))"
}

# 儀表板常駐(part-014):開機自啟,綁 127.0.0.1:7777(唯讀後台管理;內網反代對外)
$DashName = "$TaskPrefix-dashboard"
$DashRunner = Join-Path $PSScriptRoot "run_dashboard.cmd"
cmd /c "schtasks /Delete /TN $DashName /F >nul 2>&1"
$dtr = '\"' + $DashRunner + '\"'
cmd /c "schtasks /Create /TN $DashName /TR `"$dtr`" /SC ONSTART /RL LIMITED /F >nul"
if ($LASTEXITCODE -eq 0) { Write-Host "registered: $DashName (唯讀儀表板 127.0.0.1:7777,開機自啟)" }

Write-Host ""
Write-Host "全部註冊完成。檢查:schtasks /Query /TN MyAgent-remind"
Write-Host "儀表板:現在啟動 → schtasks /Run /TN MyAgent-dashboard;開 http://127.0.0.1:7777"
Write-Host "健康檢查:python -m core.stm --db C:\Users\tcart\my-agent-data\state.db advices list"
Write-Host "(回來後設 MY_AGENT_LLM_API_KEY User 環境變數,LLM jobs 自動恢復)"
