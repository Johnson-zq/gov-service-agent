# Start the local Backend with one process-scoped LLM API key.
# The key is read from this PowerShell process only and removed when Uvicorn exits.
# It is not written to .env, a file, or the git history.

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
    & python -m uvicorn gov_service_agent.main:app --host 127.0.0.1 --port 8000
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
