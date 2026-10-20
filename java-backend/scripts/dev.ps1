param(
    [ValidateSet('Run', 'Test', 'Package')]
    [string]$Action = 'Run',
    [string]$JavaHome = $env:PAPERFLOW_JAVA_HOME
)

$ErrorActionPreference = 'Stop'
$phase2ProjectRoot = Split-Path -Parent $PSScriptRoot

function Get-ProjectJavaMajor([string]$Candidate) {
    if (-not $Candidate) { return 0 }
    $phase2JavaExe = Join-Path $Candidate 'bin\java.exe'
    if (-not (Test-Path -LiteralPath $phase2JavaExe)) { return 0 }
    $phase2JavaStart = New-Object System.Diagnostics.ProcessStartInfo
    $phase2JavaStart.FileName = $phase2JavaExe
    $phase2JavaStart.Arguments = '-version'
    $phase2JavaStart.UseShellExecute = $false
    $phase2JavaStart.CreateNoWindow = $true
    $phase2JavaStart.RedirectStandardOutput = $true
    $phase2JavaStart.RedirectStandardError = $true
    $phase2JavaProcess = [System.Diagnostics.Process]::Start($phase2JavaStart)
    try {
        $phase2Version = $phase2JavaProcess.StandardError.ReadToEnd() + $phase2JavaProcess.StandardOutput.ReadToEnd()
        $phase2JavaProcess.WaitForExit()
    } finally {
        $phase2JavaProcess.Dispose()
    }
    if ($phase2Version -match 'version "(\d+)(?:\.(\d+))?') {
        if ([int]$Matches[1] -eq 1) { return [int]$Matches[2] }
        return [int]$Matches[1]
    }
    return 0
}

$phase2Candidates = @()
if ($JavaHome) {
    $phase2Candidates = @($JavaHome)
} else {
    if ($env:JAVA_HOME) { $phase2Candidates += $env:JAVA_HOME }
    $phase2JdkDirectory = Join-Path $env:USERPROFILE '.jdks'
    if (Test-Path -LiteralPath $phase2JdkDirectory) {
        $phase2Candidates += @(Get-ChildItem -LiteralPath $phase2JdkDirectory -Directory |
            Sort-Object Name -Descending | Select-Object -ExpandProperty FullName)
    }
    $phase2Javac = Get-Command javac.exe -ErrorAction SilentlyContinue
    if ($phase2Javac) {
        $phase2Candidates += Split-Path -Parent (Split-Path -Parent $phase2Javac.Source)
    }
}

$phase2SelectedJdk = $null
foreach ($phase2Candidate in $phase2Candidates) {
    $phase2Major = Get-ProjectJavaMajor $phase2Candidate
    if ($phase2Major -ge 21 -and $phase2Major -le 25) {
        $phase2SelectedJdk = $phase2Candidate
        break
    }
}
if (-not $phase2SelectedJdk) {
    throw 'A JDK from 21 through 25 is required. Set PAPERFLOW_JAVA_HOME to its installation directory.'
}

$phase2OriginalJavaHome = $env:JAVA_HOME
$phase2ExitCode = 1
try {
    $env:JAVA_HOME = $phase2SelectedJdk
    Write-Host "Project JDK: $phase2SelectedJdk"
    Push-Location $phase2ProjectRoot
    $phase2Arguments = @('-B', '-ntp')
    switch ($Action) {
        'Test' { $phase2Arguments += 'test' }
        'Package' { $phase2Arguments += 'package' }
        'Run' { $phase2Arguments += @('spring-boot:run', '-Dspring-boot.run.profiles=local') }
    }
    & (Join-Path $phase2ProjectRoot 'mvnw.cmd') @phase2Arguments
    $phase2ExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:JAVA_HOME = $phase2OriginalJavaHome
}
exit $phase2ExitCode
