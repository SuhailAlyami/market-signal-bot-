param(
    [string]$PythonExe = (Join-Path $env:LOCALAPPDATA 'SuhailHunterResearch\runtime\Scripts\python.exe'),
    [string]$State = (Join-Path $env:LOCALAPPDATA 'SuhailHunterResearch\availability')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$worker = Join-Path $repo 'spx_availability_recorder.py'
$publish = Join-Path (Split-Path $repo -Parent) 'suhail-spx-agent\.hunter-state\spx-availability'
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Existing research Python runtime missing; no new packages installed.' }
$pythonw = Join-Path (Split-Path $PythonExe -Parent) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'Existing pythonw.exe is required.' }
if (-not (Test-Path -LiteralPath $worker)) { throw 'Availability recorder source missing.' }
if (-not (Test-Path -LiteralPath (Split-Path (Split-Path $publish -Parent) -Parent))) { throw 'Installed research worktree missing.' }
New-Item -ItemType Directory -Force -Path $State | Out-Null
$launcher = Join-Path $State 'launch_availability.py'
$existing = Get-ScheduledTask -TaskName 'Suhail SPX Availability' -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Execute -ne $pythonw -or $existing.Actions.Arguments -ne ('"{0}"' -f $launcher))) {
    throw 'Existing task has different settings; preserved it without replacement.'
}
$pyWorker = ConvertTo-Json $worker -Compress
$pyState = ConvertTo-Json $State -Compress
$pyPublish = ConvertTo-Json $publish -Compress
$source = @"
import os, runpy, sys
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.argv = [$pyWorker, '--state', $pyState, '--publish-root', $pyPublish, '--port', '4001', '--client-id', '20331027']
sys.path.insert(0, os.path.dirname($pyWorker))
with open(os.path.join($pyState, 'recorder.log'), 'a', encoding='utf-8') as log:
    sys.stdout = sys.stderr = log
    runpy.run_path($pyWorker, run_name='__main__')
"@
[IO.File]::WriteAllText($launcher, $source, (New-Object Text.UTF8Encoding $false))
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}"' -f $launcher) -WorkingDirectory $repo
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15))
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Suhail SPX Availability' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'Suhail SPX Availability'
Write-Host 'Started native SPX availability observation using existing runtime/Gateway; no model invocation, trade, paid service or alert test.'
Write-Host "State: $State"
