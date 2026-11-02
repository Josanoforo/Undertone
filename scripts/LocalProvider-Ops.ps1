function Resolve-LocalPowerShell([string]$Path) {
    # Resolve the running executable, not a guessed powershell.exe beneath PSHOME.
    if (-not $Path) { $Path = (Get-Process -Id $PID -ErrorAction Stop).Path }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "PowerShell executable not found: $Path. No process was started." }
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).ProviderPath
    if ([IO.Path]::GetFileName($resolved) -notin @('powershell.exe','pwsh.exe')) { throw 'Executable must be powershell.exe or pwsh.exe. No process was started.' }
    return $resolved
}
function Get-DetachedLocalEnvironmentNames {
    # WMI does not inherit the caller environment. Persist only non-secret settings.
    return @('PATH','APP_HOST','APP_PORT','APP_DATA_DIR','APP_CLIENT_DIR','APP_ALLOWED_HOSTS','APP_PUBLIC_ORIGIN',
        'OLLAMA_URL','OLLAMA_MODEL','ASR_PYTHON','ASR_MODEL_PATH','ASR_LANGUAGE')
}
function Invoke-WithLocalTwitchCredentials {
    param([string]$AppRoot,[scriptblock]$Action)
    $idSecure=$null; $secretSecure=$null; $bundle=$null
    $oldId=[Environment]::GetEnvironmentVariable('TWITCH_CLIENT_ID','Process')
    $oldSecret=[Environment]::GetEnvironmentVariable('TWITCH_CLIENT_SECRET','Process')
    try {
        try {
            $file=Get-Item -LiteralPath (Join-Path $AppRoot '.runtime\mesa02\credentials\twitch-app.dpapi.json') -Force -ErrorAction Stop
            if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe credential file.' }
            $bundle=Get-Content -Raw -LiteralPath $file.FullName -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            if ($bundle.schema -cne 'twitch-app-credential/v1' -or $bundle.clientIdProtected -isnot [string] -or $bundle.clientSecretProtected -isnot [string]) { throw 'Invalid credential schema.' }
            $idSecure=ConvertTo-SecureString $bundle.clientIdProtected -ErrorAction Stop
            $secretSecure=ConvertTo-SecureString $bundle.clientSecretProtected -ErrorAction Stop
            $env:TWITCH_CLIENT_ID=[Net.NetworkCredential]::new('', $idSecure).Password
            $env:TWITCH_CLIENT_SECRET=[Net.NetworkCredential]::new('', $secretSecure).Password
            if ([string]::IsNullOrWhiteSpace($env:TWITCH_CLIENT_ID) -or [string]::IsNullOrWhiteSpace($env:TWITCH_CLIENT_SECRET)) { throw 'Empty protected credential.' }
        } catch { throw 'Protected Twitch configuration could not be loaded for this Windows account.' }
        & $Action
    } finally {
        [Environment]::SetEnvironmentVariable('TWITCH_CLIENT_ID',$oldId,'Process')
        [Environment]::SetEnvironmentVariable('TWITCH_CLIENT_SECRET',$oldSecret,'Process')
        if ($idSecure) { $idSecure.Dispose() }; if ($secretSecure) { $secretSecure.Dispose() }
        $bundle=$null; $oldId=$null; $oldSecret=$null
    }
}
function Start-DetachedLocal {
    param([string]$AppRoot,[string]$Provider,[string]$LaunchName,[string]$PowerShellPath,[switch]$ProtectedTwitch)
    $shell = Resolve-LocalPowerShell $PowerShellPath
    $wrapper = Join-Path $AppRoot 'scripts\Invoke-DetachedLocal.ps1'
    $launcher = Join-Path $AppRoot 'scripts\Start-Local.ps1'
    if (-not (Test-Path -LiteralPath $AppRoot -PathType Container)) { throw 'Launch working directory not found. No process was started.' }
    foreach ($file in @($wrapper,$launcher)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Launch wrapper or launcher not found: $file. No process was started." }
    }
    $name = if ($LaunchName) { $LaunchName } else { 'LOCAL-' + [guid]::NewGuid().ToString('N') }
    if ($name -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid launch name.' }
    $directory = Join-Path $AppRoot ('.runtime\detached\' + $name)
    if ((Test-Path -LiteralPath $directory) -or (Test-Path -LiteralPath (Join-Path $AppRoot ('.runtime\run\' + $name)))) { throw 'Launch run already exists.' }
    $requestPath = Join-Path $directory 'request.json'
    foreach ($path in @($shell,$wrapper,$AppRoot,$requestPath)) {
        if ($path -match '["\r\n]') { throw 'Invalid character in launch path. No process was started.' }
    }
    $settings = @{}
    foreach ($key in (Get-DetachedLocalEnvironmentNames)) { $settings[$key] = [Environment]::GetEnvironmentVariable($key,'Process') }
    # Complete path validation above precedes all writes and process creation.
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
    @{runName=$name;provider=$Provider;protectedTwitch=[bool]$ProtectedTwitch;environment=$settings} |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $requestPath -Encoding utf8
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine=('"{0}" -NoProfile -NonInteractive -File "{1}" -RequestPath "{2}"' -f $shell,$wrapper,$requestPath)
        CurrentDirectory=$AppRoot;ProcessStartupInformation=$startup
    } -ErrorAction Stop
    $creation = [ordered]@{returnValue=[int]$created.ReturnValue;wrapperPid=[int]$created.ProcessId;executable=$shell;wrapper=$wrapper;workingDirectory=$AppRoot;runName=$name}
    $creation | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'creation.json') -Encoding utf8
    if ($created.ReturnValue -ne 0) {
        $reason = switch ([int]$created.ReturnValue) { 9 {'Path not found'} 2 {'Access denied'} default {'Process creation failed'} }
        throw "Win32_Process.Create ReturnValue=$($created.ReturnValue): $reason. Inspect $directory."
    }
    $statusPath = Join-Path $directory 'status.json'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $statusPath)) {
        if ($timer.Elapsed.TotalSeconds -gt 90) { throw "Detached launcher status timed out; creation succeeded. Do not relaunch blindly. Inspect $directory." }
        Start-Sleep -Milliseconds 250
    }
    $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
    if ($status.exitCode -ne 0) { throw "Detached launcher failed (exitCode=$($status.exitCode), stage=$($status.stage)). Inspect $directory and .runtime/run/$name; no process was stopped." }
    [ordered]@{runName=$name;wrapperPid=[int]$created.ProcessId;creationReturnValue=[int]$created.ReturnValue;manifest=(Join-Path $AppRoot ('.runtime\run\'+$name+'\launch.json'));logs=$directory;launcherExitCode=$status.exitCode} | ConvertTo-Json
}
function Read-LocalClaudeKey([string]$Path) {
    $secure=$null; $ptr=[IntPtr]::Zero
    try {
        $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($Path).Trim())
        $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $value=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        if (-not $value) { throw 'Credential is empty.' }
        return $value
    } finally {
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        if ($secure) { $secure.Dispose() }
    }
}
function Start-ScopedBackend($Python,$WorkingDirectory,$Stdout,$Stderr,$Variables,$State,[bool]$Foreground=$false) {
    $prior=@{}
    foreach ($name in $Variables.Keys) { $prior[$name]=[Environment]::GetEnvironmentVariable($name,'Process') }
    try {
        foreach ($name in $Variables.Keys) { [Environment]::SetEnvironmentVariable($name,$Variables[$name],'Process') }
        $State.phase='creating'
        $args=@{FilePath=$Python;ArgumentList=@('-m','server');WorkingDirectory=$WorkingDirectory;PassThru=$true;RedirectStandardOutput=$Stdout;RedirectStandardError=$Stderr;ErrorAction='Stop'}
        if ($Foreground) { $args.NoNewWindow=$true } else { $args.WindowStyle='Hidden' }
        $child=Start-Process @args
        $State.pid=$child.Id; $State.startedAtUtc=$child.StartTime.ToUniversalTime().ToString('o');$State.python=$Python; $State.phase='created'
        return $child
    } finally {
        foreach ($name in $prior.Keys) { [Environment]::SetEnvironmentVariable($name,$prior[$name],'Process') }
    }
}
function Get-ListenerOwners([int]$Port) {
    try { $rows=@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop) }
    catch { if ($_.FullyQualifiedErrorId -match '^CmdletizationQuery_NotFound(?:,|$)') { return @() }; throw }
    $owners=@()
    foreach ($row in $rows) {
        if ($null -eq $row -or $null -eq $row.RemotePort -or $null -eq $row.RemoteAddress -or $null -eq $row.OwningProcess) { throw 'Cannot inspect listener tuple.' }
        $remotePort=0; $owner=0; $remoteAddress=$null
        if ([string]$row.RemotePort -notmatch '^\d+$' -or -not [int]::TryParse([string]$row.RemotePort,[ref]$remotePort) -or $remotePort -gt 65535 -or
            [string]$row.OwningProcess -notmatch '^\d+$' -or -not [int]::TryParse([string]$row.OwningProcess,[ref]$owner) -or
            -not [Net.IPAddress]::TryParse([string]$row.RemoteAddress,[ref]$remoteAddress)) { throw 'Cannot inspect listener tuple.' }
        if ($remotePort -eq 0 -and ($remoteAddress.Equals([Net.IPAddress]::Any) -or $remoteAddress.Equals([Net.IPAddress]::IPv6Any))) { $owners += $owner }
    }
    return @($owners | Sort-Object -Unique)
}
function Stop-OwnUnreadyChild($State,[int]$Port) {
    if ($State.phase -ne 'created' -or -not $State.pid -or -not $State.startedAtUtc) { throw 'Child identity unavailable.' }
    $owners=@(Get-ListenerOwners $Port)
    if (@($owners | Where-Object {$_ -ne [int]$State.pid}).Count -gt 0) { throw 'Foreign listener; no process stopped.' }
    $proc=Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if (-not $proc) { return }
    if ([IO.Path]::GetFullPath($proc.Path) -ne [IO.Path]::GetFullPath([string]$State.python)) { throw 'Child executable mismatch.' }
    if ([Math]::Abs(($proc.StartTime.ToUniversalTime()-([DateTimeOffset]::Parse([string]$State.startedAtUtc)).UtcDateTime).TotalSeconds) -gt 2) { throw 'Child start mismatch.' }
    $info=Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.pid)" -ErrorAction Stop
    $pattern=[regex]::Escape([string]$State.python)
    if (-not $info -or [IO.Path]::GetFullPath($info.ExecutablePath) -ne [IO.Path]::GetFullPath([string]$State.python) -or $info.CommandLine -notmatch ('^(?:"'+$pattern+'"|'+$pattern+')\s+-m\s+server\s*$')) { throw 'Child command mismatch.' }
    Stop-Process -Id ([int]$State.pid) -ErrorAction Stop
    Wait-Process -Id ([int]$State.pid) -Timeout 10 -ErrorAction SilentlyContinue
    if (Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue) { throw 'Child did not stop within timeout.' }
    if (@(Get-ListenerOwners $Port).Count -ne 0) { throw 'Listener remains after child stopped.' }
}
function Invoke-PreStop([scriptblock]$Preflight,[scriptblock]$Stop) {
    & $Preflight
    & $Stop
}
function Resolve-FailedLaunch($State,[int]$Port) {
    if ($State.phase -eq 'created') { Stop-OwnUnreadyChild $State $Port }
    elseif ($State.phase -ne 'before') { throw 'Child creation outcome unknown; rollback requires operator inspection.' }
    if (@(Get-ListenerOwners $Port).Count -ne 0) { throw 'Rollback blocked: listener is owned.' }
    return 'rollback_allowed'
}
function New-RollbackEnvironment($Manifest,$Asr,[int]$Port,[string]$DataDir) {
    if (-not $Manifest.model) { throw 'Original Ollama model missing.' }
    return @{APP_HOST='127.0.0.1';APP_PORT=[string]$Port;APP_DATA_DIR=$DataDir;ASR_PYTHON=[string]$Asr.python;ASR_MODEL_PATH=[string]$Asr.modelPath;ASR_LANGUAGE=[string]$Asr.language;ANTHROPIC_API_KEY=$null;APP_AI_PROVIDER='ollama';OLLAMA_MODEL=[string]$Manifest.model}
}
