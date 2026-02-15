param(
    [ValidateSet(
        'help',
        'brain-start','brain-stop','brain-status','brain-once','brain-dream-once','brain-debate-once',
        'deep-worker-start','deep-worker-stop','deep-worker-status','deep-worker-once','deep-worker-force-deep','deep-worker-force-dream',
        'health-start','health-stop','health-status','health-once',
        'web-probe-start','web-probe-stop','web-probe-status','web-probe-once',
        'file-feed-start','file-feed-stop','file-feed-status','file-feed-once',
        'vscode-start','vscode-stop','vscode-status','vscode-once',
        'social-start','social-stop','social-status','social-once',
        'shallow-start','shallow-stop','shallow-status','shallow-once',
        'device-capture-start','device-capture-stop','device-capture-status',
        'brain-web',
        'mcp-github-demo',
        'conscious-report','conscious-report-json',
        'stack-start','stack-start-lite','stack-start-full-delayed','stack-stop','stack-status','stack-restart'
    )]
    [string]$Task = 'help'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Run-Step {
    param([string]$Title, [string]$Command)
    Write-Host "`n== $Title ==" -ForegroundColor Cyan
    Write-Host $Command -ForegroundColor DarkGray
    Invoke-Expression $Command
}

switch ($Task) {
    'help' {
        Write-Host 'Azi Rebuild task runner' -ForegroundColor Green
        Write-Host 'Usage: .\run.ps1 -Task <task>'
        Write-Host 'Tasks:'
        Write-Host '  brain-start / brain-stop / brain-status / brain-once'
        Write-Host '  brain-dream-once / brain-debate-once'
        Write-Host '  deep-worker-start / deep-worker-stop / deep-worker-status / deep-worker-once'
        Write-Host '  deep-worker-force-deep / deep-worker-force-dream'
        Write-Host '  health-start / health-stop / health-status / health-once'
        Write-Host '  web-probe-start / web-probe-stop / web-probe-status / web-probe-once'
        Write-Host '  file-feed-start / file-feed-stop / file-feed-status / file-feed-once'
        Write-Host '  vscode-start / vscode-stop / vscode-status / vscode-once'
        Write-Host '  social-start / social-stop / social-status / social-once'
        Write-Host '  shallow-start / shallow-stop / shallow-status / shallow-once'
        Write-Host '  device-capture-start / device-capture-stop / device-capture-status'
        Write-Host '  brain-web'
        Write-Host '  mcp-github-demo'
        Write-Host '  conscious-report / conscious-report-json'
        Write-Host '  stack-start / stack-start-lite / stack-start-full-delayed'
        Write-Host '  stack-stop / stack-status / stack-restart'
    }

    'brain-start' { Run-Step 'Brain Loop Start' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action start' }
    'brain-stop' { Run-Step 'Brain Loop Stop' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action stop' }
    'brain-status' { Run-Step 'Brain Loop Status' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action status' }
    'brain-once' { Run-Step 'Brain Loop Run Once' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action run-once' }
    'brain-dream-once' { Run-Step 'Brain Loop Run Once (Force Dream)' 'python .\brain_loop.py --db azi_rebuild.db --state azi_state.json --once --max-events 12 --force-dream' }
    'brain-debate-once' { Run-Step 'Brain Loop Run Once (Force Debate)' 'python .\brain_loop.py --db azi_rebuild.db --state azi_state.json --once --max-events 12 --force-debate' }

    'deep-worker-start' { Run-Step 'Deep Worker Start' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action start' }
    'deep-worker-stop' { Run-Step 'Deep Worker Stop' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action stop' }
    'deep-worker-status' { Run-Step 'Deep Worker Status' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action status' }
    'deep-worker-once' { Run-Step 'Deep Worker Run Once' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action run-once' }
    'deep-worker-force-deep' { Run-Step 'Deep Worker Run Once (Force Deep)' 'python .\deep_coder_worker.py --db azi_rebuild.db --state azi_state.json --once --force-deep' }
    'deep-worker-force-dream' { Run-Step 'Deep Worker Run Once (Force Dream)' 'python .\deep_coder_worker.py --db azi_rebuild.db --state azi_state.json --once --force-dream' }

    'health-start' { Run-Step 'Health Checker Start' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action start' }
    'health-stop' { Run-Step 'Health Checker Stop' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action stop' }
    'health-status' { Run-Step 'Health Checker Status' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action status' }
    'health-once' { Run-Step 'Health Checker Run Once' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action run-once' }

    'web-probe-start' { Run-Step 'Web Probe Start' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action start' }
    'web-probe-stop' { Run-Step 'Web Probe Stop' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action stop' }
    'web-probe-status' { Run-Step 'Web Probe Status' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action status' }
    'web-probe-once' { Run-Step 'Web Probe Run Once' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action run-once' }

    'file-feed-start' { Run-Step 'File Feed Start' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action start' }
    'file-feed-stop' { Run-Step 'File Feed Stop' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action stop' }
    'file-feed-status' { Run-Step 'File Feed Status' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action status' }
    'file-feed-once' { Run-Step 'File Feed Run Once' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action run-once' }

    'vscode-start' { Run-Step 'VSCode Observer Start' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action start' }
    'vscode-stop' { Run-Step 'VSCode Observer Stop' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action stop' }
    'vscode-status' { Run-Step 'VSCode Observer Status' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action status' }
    'vscode-once' { Run-Step 'VSCode Observer Run Once' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action run-once' }

    'social-start' { Run-Step 'Social Bridge Start' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action start' }
    'social-stop' { Run-Step 'Social Bridge Stop' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action stop' }
    'social-status' { Run-Step 'Social Bridge Status' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action status' }
    'social-once' { Run-Step 'Social Bridge Run Once' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action run-once' }

    'shallow-start' { Run-Step 'Shallow Thinker Start' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action start' }
    'shallow-stop' { Run-Step 'Shallow Thinker Stop' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action stop' }
    'shallow-status' { Run-Step 'Shallow Thinker Status' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action status' }
    'shallow-once' { Run-Step 'Shallow Thinker Run Once' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action run-once' }

    'device-capture-start' { Run-Step 'Device Capture Server Start' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action start' }
    'device-capture-stop' { Run-Step 'Device Capture Server Stop' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action stop' }
    'device-capture-status' { Run-Step 'Device Capture Server Status' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action status' }

    'brain-web' {
        Run-Step 'Brain Web Panel' 'python brain_web_panel.py --db azi_rebuild.db --state azi_state.json --host 127.0.0.1 --port 8798'
    }

    'mcp-github-demo' {
        Run-Step 'MCP GitHub Demo (search + inject)' 'powershell -ExecutionPolicy Bypass -File .\mcp_github_demo.ps1'
    }
    'conscious-report' {
        Run-Step 'Engineering Consciousness Report' 'python .\consciousness_report.py --db .\azi_rebuild.db'
    }
    'conscious-report-json' {
        Run-Step 'Engineering Consciousness Report (write json)' 'python .\consciousness_report.py --db .\azi_rebuild.db --write-json .\resident_output\consciousness_report.json'
    }

    'stack-start-lite' {
        Run-Step 'Brain Loop Start' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action start'
        Run-Step 'Deep Worker Start' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action start'
        Run-Step 'Open Brain Web Panel (detached)' "`$exists = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { (`$_.Name -in @('python.exe','pythonw.exe')) -and (`$_.CommandLine -like '*brain_web_panel.py*') -and (`$_.CommandLine -like '*azi_rebuild.db*') }; if (-not `$exists) { Start-Process -FilePath python -ArgumentList 'brain_web_panel.py --db azi_rebuild.db --state azi_state.json --host 127.0.0.1 --port 8798' -WorkingDirectory '$root' -WindowStyle Hidden } else { Write-Host 'Brain Web Panel already running.' }"
        Run-Step 'Open Brain Web Frontend' "Start-Process 'http://127.0.0.1:8798'"
    }

    'stack-start-full-delayed' {
        Run-Step 'Core Stack Start' 'powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start-lite'
        Run-Step 'Health Checker Start' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action start'
        Run-Step 'Web Probe Start' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action start'
        Run-Step 'File Feed Start' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action start'
        Run-Step 'VSCode Observer Start' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action start'
        Run-Step 'Social Bridge Start' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action start'
        Run-Step 'Shallow Thinker Start' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action start'
        Run-Step 'Device Capture Server Start' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action start'
    }

    'stack-start' {
        Run-Step 'Stack Start (Full)' 'powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start-full-delayed'
    }

    'stack-stop' {
        Run-Step 'Web Probe Stop' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action stop'
        Run-Step 'File Feed Stop' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action stop'
        Run-Step 'VSCode Observer Stop' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action stop'
        Run-Step 'Social Bridge Stop' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action stop'
        Run-Step 'Shallow Thinker Stop' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action stop'
        Run-Step 'Device Capture Server Stop' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action stop'
        Run-Step 'Brain Loop Stop' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action stop'
        Run-Step 'Deep Worker Stop' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action stop'
        Run-Step 'Health Checker Stop' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action stop'
        Run-Step 'Brain Web Panel Stop' "`$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { (`$_.Name -in @('python.exe','pythonw.exe')) -and (`$_.CommandLine -like '*brain_web_panel.py*') -and (`$_.CommandLine -like '*azi_rebuild.db*') }); if (`$procs.Count -gt 0) { `$procs | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host ('Brain Web Panel stopped: ' + `$procs.Count) } else { Write-Host 'Brain Web Panel not running.' }"
    }

    'stack-status' {
        Run-Step 'Brain Loop Status' 'powershell -ExecutionPolicy Bypass -File .\brain_control.ps1 -Action status'
        Run-Step 'Deep Worker Status' 'powershell -ExecutionPolicy Bypass -File .\deep_coder_control.ps1 -Action status'
        Run-Step 'Health Checker Status' 'powershell -ExecutionPolicy Bypass -File .\health_check_control.ps1 -Action status'
        Run-Step 'Web Probe Status' 'powershell -ExecutionPolicy Bypass -File .\web_probe_control.ps1 -Action status'
        Run-Step 'File Feed Status' 'powershell -ExecutionPolicy Bypass -File .\file_feed_control.ps1 -Action status'
        Run-Step 'VSCode Observer Status' 'powershell -ExecutionPolicy Bypass -File .\vscode_observer_control.ps1 -Action status'
        Run-Step 'Social Bridge Status' 'powershell -ExecutionPolicy Bypass -File .\social_control.ps1 -Action status'
        Run-Step 'Shallow Thinker Status' 'powershell -ExecutionPolicy Bypass -File .\shallow_think_control.ps1 -Action status'
        Run-Step 'Device Capture Server Status' 'powershell -ExecutionPolicy Bypass -File .\device_capture_control.ps1 -Action status'
        Run-Step 'Brain Web Panel Status' "`$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { (`$_.Name -in @('python.exe','pythonw.exe')) -and (`$_.CommandLine -like '*brain_web_panel.py*') -and (`$_.CommandLine -like '*azi_rebuild.db*') }); if (`$procs.Count -gt 0) { Write-Host ('Brain Web Panel running: ' + `$procs.Count + ' process(es)') } else { Write-Host 'Brain Web Panel not running.' }"
    }

    'stack-restart' {
        Run-Step 'Stack Stop' 'powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-stop'
        Run-Step 'Stack Start' 'powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start'
    }
}
