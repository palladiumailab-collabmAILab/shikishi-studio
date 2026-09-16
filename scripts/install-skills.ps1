[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$CodexSkillsRoot,
    [string[]]$Name = @('repo-research', 'github-operations', 'self-improvement', 'long-running-work'),
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$resolvedRepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$sourceRoot = Join-Path $resolvedRepositoryRoot 'skills'
$resolvedSkillsRoot = (Resolve-Path -LiteralPath $CodexSkillsRoot).Path

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Skills directory was not found: $sourceRoot"
}

$requestedNames = @($Name | Sort-Object -Unique)
if ($requestedNames.Count -eq 0) {
    throw 'At least one skill name must be specified.'
}

$availableNames = @(Get-ChildItem -LiteralPath $sourceRoot -Directory | Select-Object -ExpandProperty Name)
$missing = @($requestedNames | Where-Object { $_ -notin $availableNames })
if ($missing.Count -gt 0) {
    throw "Unknown skill name(s): $($missing -join ', ')"
}

$existing = @(
    $requestedNames |
        Where-Object { Test-Path -LiteralPath (Join-Path $resolvedSkillsRoot $_) }
)
if ($existing.Count -gt 0) {
    throw "Refusing to overwrite existing skill directories: $($existing -join ', ')"
}

foreach ($skillName in $requestedNames) {
    $source = Join-Path $sourceRoot $skillName
    $destination = Join-Path $resolvedSkillsRoot $skillName
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
    Write-Output "Installed skill: $skillName"
}
