# coding-agent-setup installer (Windows PowerShell 7+).
#
# Sets up a codebase for token-efficient agent development:
#   1. CodeGraph  — symbol/call-graph MCP server
#   2. RTK        — shell-output compressor
#   3. Config     — MCP registration + RTK hook/nudge + project instructions
#   4. DOX        — seed a root AGENTS.md architecture contract (place-before-building)
#
# Idempotent and non-destructive: merges into existing config, never overwrites.
# Run from the target repo root, or pass -Repo <path>.
#   pwsh coding-agent-setup/install.ps1 [-Repo C:\path\to\repo]
#
# Toggles: -SkipCodegraph  -SkipRtk  -SkipConfig  -SkipDox

param(
  [string]$Repo = (Get-Location).Path,
  [switch]$SkipCodegraph,
  [switch]$SkipRtk,
  [switch]$SkipConfig,
  [switch]$SkipDox
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Templates = Join-Path $ScriptDir "templates"
$Repo = (Resolve-Path $Repo).Path

function Say  ($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Ok   ($m) { Write-Host "  ok   $m" -ForegroundColor Green }
function Skip ($m) { Write-Host " skip  $m" -ForegroundColor Yellow }
function Warn ($m) { Write-Host " warn  $m" -ForegroundColor Red }
function Have ($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }

# Deep-merge $Add into JSON file at $Target; never clobbers existing keys.
function Merge-Json ($Target, $Add) {
  $cur = @{}
  if (Test-Path $Target) {
    try { $cur = Get-Content $Target -Raw | ConvertFrom-Json -AsHashtable }
    catch { Warn "existing $Target is not valid JSON; leaving untouched"; return }
  }
  function DeepMerge ($dst, $src) {
    foreach ($k in $src.Keys) {
      if ($dst.ContainsKey($k) -and ($dst[$k] -is [hashtable]) -and ($src[$k] -is [hashtable])) {
        DeepMerge $dst[$k] $src[$k]
      } elseif (-not $dst.ContainsKey($k)) {
        $dst[$k] = $src[$k]
      }
    }
  }
  DeepMerge $cur $Add
  $dir = Split-Path -Parent $Target
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  ($cur | ConvertTo-Json -Depth 20) | Set-Content -Path $Target -Encoding utf8
}

Say "target repo: $Repo"
Set-Location $Repo

$CG = @{ type = "stdio"; command = "codegraph"; args = @("serve", "--mcp") }

# ===================================================== 1. CodeGraph ==========
if ($SkipCodegraph) { Skip "CodeGraph (-SkipCodegraph)" }
else {
  if (-not (Have codegraph)) {
    if (Have npm) {
      Say "installing CodeGraph CLI (npm -g @colbymchenry/codegraph)"
      npm install -g @colbymchenry/codegraph 2>&1 | Out-Null
      if (Have codegraph) { Ok "CodeGraph installed ($(codegraph --version))" } else { Warn "npm install failed" }
    } else { Warn "npm not found — install Node.js >=18, then: npm i -g @colbymchenry/codegraph" }
  } else { Ok "CodeGraph already present ($(codegraph --version))" }

  if (Have codegraph) {
    $cgJson = Join-Path $Templates "shared\codegraph.json"
    if ((-not (Test-Path "codegraph.json")) -and (Test-Path $cgJson)) {
      Copy-Item $cgJson "codegraph.json"; Ok "wrote codegraph.json (edit exclude list)"
    } else { Skip "codegraph.json exists" }
    if (-not (Test-Path ".codegraph")) {
      Say "building initial index (codegraph init)"
      codegraph init . 2>&1 | Out-Null
      if (Test-Path ".codegraph") { Ok "index built" } else { Warn "codegraph init failed" }
    } else { Skip ".codegraph index exists (run 'codegraph sync .')" }
  }
}

# ===================================================== 2. RTK ================
if ($SkipRtk) { Skip "RTK (-SkipRtk)" }
elseif (Have rtk) { Ok "RTK already present ($(rtk --version))" }
else {
  Say "installing RTK"
  if (Have winget) {
    winget install rtk-ai.rtk --exact --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1 | Out-Null
  } elseif (Have cargo) { cargo install --git https://github.com/rtk-ai/rtk 2>&1 | Out-Null }
  else { Warn "no winget/cargo — install rtk from https://www.rtk-ai.app" }
  if (Have rtk) { Ok "RTK installed ($(rtk --version))" } else { Warn "RTK not on PATH (open a new shell)" }
}

# ===================================================== 3. Config =============
if ($SkipConfig) { Skip "config (-SkipConfig)" }
else {
  Merge-Json ".mcp.json"        @{ mcpServers = @{ codegraph = $CG } }; Ok ".mcp.json (Claude Code MCP)"
  Merge-Json ".vscode\mcp.json" @{ servers    = @{ codegraph = $CG } }; Ok ".vscode/mcp.json (Copilot MCP)"

  $hook = Join-Path $Templates "claude\hooks\rtk-bash.sh"
  if (Test-Path $hook) {
    New-Item -ItemType Directory -Force ".claude\hooks" | Out-Null
    Copy-Item $hook ".claude\hooks\rtk-bash.sh" -Force
    $settings = Join-Path $Templates "claude\settings.json"
    if (Test-Path $settings) { Merge-Json ".claude\settings.json" ((Get-Content $settings -Raw) | ConvertFrom-Json -AsHashtable) }
    Ok ".claude/ RTK hook + settings"
  }

  $cpi = ".github\copilot-instructions.md"
  $block = Join-Path $Templates "copilot\copilot-instructions-rtk-block.md"
  if (Test-Path $block) {
    New-Item -ItemType Directory -Force ".github" | Out-Null
    if ((Test-Path $cpi) -and (Select-String -Path $cpi -Pattern "prefix noisy commands with ``rtk``" -Quiet)) {
      Skip "copilot-instructions.md already has RTK block"
    } else {
      "`n" | Add-Content $cpi
      Get-Content $block -Raw | Add-Content $cpi
      Ok "appended RTK block to $cpi"
    }
  }
}

# ===================================================== 4. DOX ===============
# Seed a root AGENTS.md "DOX" architecture contract if the repo has none.
# Non-destructive: never touches an existing AGENTS.md.
if ($SkipDox) { Skip "DOX architecture contract (-SkipDox)" }
elseif (Test-Path "AGENTS.md") { Skip "AGENTS.md exists (DOX contract already present — leaving it untouched)" }
else {
  $dox = Join-Path $Templates "shared\AGENTS.md"
  if (Test-Path $dox) {
    Copy-Item $dox "AGENTS.md"
    Ok "wrote AGENTS.md (DOX root — fill in the <...> placeholders for this repo)"
  } else { Warn "DOX template missing from kit ($dox)" }
}

# ===================================================== Verify ================
Say "verify:"
if (Have codegraph) { codegraph status . 2>&1 | Select-Object -First 3 }
if (Have rtk) { rtk --version }
Say "done. Read coding-agent-setup/SETUP.md section 6 and report the numbers."
