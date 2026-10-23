$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$agentRoot = Join-Path (Split-Path $source -Parent) 'suhail-spx-agent'
$state = Join-Path $env:LOCALAPPDATA 'SuhailHunterResearch'
$python = (Get-Command python -ErrorAction Stop).Source
$git = (Get-Command git -ErrorAction Stop).Source
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Install/sign in to Codex CLI first. The VS Code extension alone is insufficient. No API key is required by this installer.'
}
& $git -C $source fetch origin research/spx-only-price-watch-20261022
if ($LASTEXITCODE -ne 0) { throw 'GitHub fetch failed; reconnect normally.' }
if (-not (Test-Path $agentRoot)) {
    & $git -C $source worktree add -b research/local-spx-agent $agentRoot origin/research/spx-only-price-watch-20261022
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated worktree; no existing files removed.' }
}
$branch = & $git -C $agentRoot branch --show-current
if ($branch -ne 'research/local-spx-agent') { throw 'Unexpected branch; stopped.' }
$worker = Join-Path $agentRoot 'tools/spx_research_agent.py'
if (-not (Test-Path $worker)) { throw 'Fetch the published agent commit before installing.' }
New-Item -ItemType Directory -Force -Path $state | Out-Null
# Task Scheduler does not inherit the VS Code terminal PATH. Pin the resolved
# tools in a private launcher; never copy authentication or alter the user's PATH.
$codex = (Get-Command codex -ErrorAction Stop).Source
$toolPath = @((Split-Path $python), (Split-Path $git), (Split-Path $codex)) -join ';'
$quotedTools = ConvertTo-Json $toolPath -Compress
$quotedWorker = ConvertTo-Json $worker -Compress
$quotedRoot = ConvertTo-Json $agentRoot -Compress
$quotedState = ConvertTo-Json $state -Compress
$launcher = Join-Path $state 'launch_agent.py'
$launcherSource = @"
import os, runpy, sys
os.environ["PATH"] = $quotedTools + os.pathsep + os.environ.get("PATH", "")
os.environ["GIT_TERMINAL_PROMPT"] = "0"
os.environ["GCM_INTERACTIVE"] = "never"
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.argv = [$quotedWorker, "--repo", $quotedRoot, "--state", $quotedState]
with open(os.path.join($quotedState, "runner.log"), "a", encoding="utf-8") as log:
    sys.stdout = log
    sys.stderr = log
    runpy.run_path($quotedWorker, run_name="__main__")
"@
[IO.File]::WriteAllText($launcher, $launcherSource, (New-Object Text.UTF8Encoding $false))
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw 'pythonw.exe required for a hidden scheduled worker.' }
$actionArgs = '"{0}"' -f $launcher
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $actionArgs -WorkingDirectory $agentRoot
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15))
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Suhail SPX Research' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'Suhail SPX Research'
Write-Host "Installed and started. State: $state/state.json"
Write-Host 'No deployment, trades or experimental alerts enabled. Two model invocations/day maximum.'
Write-Host "Pause: New-Item -ItemType File -Path '$state/STOP'"
Write-Host "Remove: Unregister-ScheduledTask -TaskName 'Suhail SPX Research' -Confirm:`$false"
