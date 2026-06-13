<#
  run_nat.ps1 — Chạy NeMo Agent Toolkit (NAT) với key nạp tự động từ .env.

  Cách dùng (mọi tham số sẽ được chuyển thẳng cho `nat`):
    .\run_nat.ps1 run   --config_file nemo_agent_toolkit\workflow.yaml --input "Search invoices for Bjorn Hansen"
    .\run_nat.ps1 serve --config_file nemo_agent_toolkit\workflow.yaml

  Script tự: (1) đọc .env, (2) nạp biến môi trường, (3) gọi nat trong .venv.
  => Không cần set $env:NVIDIA_API_KEY bằng tay nữa.
#>

param([Parameter(ValueFromRemainingArguments = $true)] $NatArgs)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ── 1. Nạp .env ─────────────────────────────────────────────────────────────────
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "Không tìm thấy .env tại $envFile"
    exit 1
}
foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#") -or ($trimmed -notmatch "=")) { continue }
    $idx = $trimmed.IndexOf("=")
    $key = $trimmed.Substring(0, $idx).Trim()
    $val = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
    [Environment]::SetEnvironmentVariable($key, $val)
}

if (-not $env:NVIDIA_API_KEY) {
    Write-Error "NVIDIA_API_KEY chưa có trong .env"
    exit 1
}
Write-Host "[run_nat] Loaded .env (NVIDIA_API_KEY=$($env:NVIDIA_API_KEY.Substring(0,12))..., MCP_PORT=$env:MCP_PORT)" -ForegroundColor Green

# ── 2. Gọi nat trong .venv ──────────────────────────────────────────────────────
$nat = Join-Path $root ".venv\Scripts\nat.exe"
if (-not (Test-Path $nat)) { $nat = "nat" }   # fallback: nat trong PATH

# nat ghi log ra stderr -> đừng để PowerShell coi đó là lỗi và dừng.
$ErrorActionPreference = "Continue"
& $nat @NatArgs
