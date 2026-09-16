$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
git -C $repositoryRoot config core.hooksPath hooks
Write-Output 'Repository-local Git hooks are enabled.'
