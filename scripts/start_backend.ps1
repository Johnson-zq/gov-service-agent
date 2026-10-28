# Start the local Backend with one process-scoped LLM API key.
# The key is read from this PowerShell process only and removed when Uvicorn exits.
# It is not written to .env, a file, or the git history.
#
# Default port is 18000 (Windows often reserves 7998-8097, including 8000).
# Example: .\scripts\start_backend.ps1 -Port 18000

param(
    [ValidateRange(1, 65535)]
    [int]$Port = 18000
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$SecureKey = Read-Host -AsSecureString -Prompt "LLM_API_KEY (MicuAPI token, not saved)"
$Bstr = [System.IntPtr]::Zero
$PlainKey = $null
try {
    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
    $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
    if ([string]::IsNullOrWhiteSpace($PlainKey)) {
        throw "LLM_API_KEY is required. Backend was not started."
    }
    $env:LLM_API_KEY = $PlainKey
    Write-Host "Starting backend on http://127.0.0.1:$Port (LLM_API_KEY is process-scoped and will be cleared on exit)."
    & python -m uvicorn gov_service_agent.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    if ($Bstr -ne [System.IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    $PlainKey = $null
    Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue
}
