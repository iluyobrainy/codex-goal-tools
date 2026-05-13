param(
  [string]$Source = "iluyobrainy/codex-goal-tools",
  [string]$Ref = "main",
  [string]$Workspace = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found on PATH: $Name"
  }
}

Require-Command "codex"
Require-Command "python"

Write-Host "Adding Codex marketplace: $Source"
codex plugin marketplace add --ref $Ref $Source

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$backend = Join-Path $codexHome ".tmp\marketplaces\codex-goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py"

if (-not (Test-Path -LiteralPath $backend)) {
  throw "Marketplace was added, but backend script was not found: $backend"
}

Write-Host "Installing/enabling Codex Goal Tools and enabling native goals..."
python $backend bootstrap --workspace $Workspace

Write-Host ""
Write-Host "Done. Restart Codex Desktop if the skill does not appear immediately, then run:"
Write-Host '  $goal-native status'
