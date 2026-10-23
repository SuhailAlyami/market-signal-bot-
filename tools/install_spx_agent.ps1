$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$agentRoot = Join-Path (Split-Path $source -Parent) 'suhail-spx-agent'
$state = Join-Path $env:LOCALAPPDATA 'SuhailHunterResearch'
$python = (Get-Command python -ErrorAction Stop).Source
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Install/sign in to Codex CLI first. The VS Code extension alone is insufficient. No API key is required by this installer.'
}
& git -C $source fetch origin research/spx-only-price-watch-20261022
if ($LASTEXITCODE -ne 0) { throw 'GitHub fetch failed; reconnect normally.' }
if (-not (Test-Path $agentRoot)) {
    & git -C $source worktree add -b research/local-spx-agent $agentRoot origin/research/spx-only-price-watch-20261022
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated worktree; no existing files removed.' }
}
$branch = & git -C $agentRoot branch --show-current
if ($branch -ne 'research/local-spx-agent') { throw 'Unexpected branch; stopped.' }
$worker = Join-Path $agentRoot 'tools/spx_research_agent.py'
if (-not (Test-Path $worker)) { throw 'Fetch the published agent commit before installing.' }
New-Item -ItemType Directory -Force -Path $state | Out-Null
$actionArgs = '"{0}" --repo "{1}" --state "{2}"' -f $worker, $agentRoot, $state
$action = New-ScheduledTaskAction -Execute $python -Argument $actionArgs -WorkingDirectory $agentRoot
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
