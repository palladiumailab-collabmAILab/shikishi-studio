param(
    [string]$SourcePath = "kaggle/illustrious_xl_style_lora.py",
    [string]$NotebookPath = "kaggle/illustrious_xl_style_lora.ipynb"
)

$ErrorActionPreference = "Stop"
$source = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $SourcePath))
$lines = $source -split "\r?\n"
$blocks = [System.Collections.Generic.List[object]]::new()
$currentType = "code"
$currentLines = [System.Collections.Generic.List[string]]::new()

function Add-Block {
    param(
        [string]$CellType,
        [System.Collections.Generic.List[string]]$CellLines
    )
    if ($CellLines.Count -eq 0) {
        return
    }
    $blocks.Add([pscustomobject]@{ Type = $CellType; Lines = $CellLines.ToArray() })
}

foreach ($line in $lines) {
    if ($line -match '^# %%(?: \[(markdown)\])?$') {
        Add-Block -CellType $currentType -CellLines $currentLines
        $currentType = if ($Matches[1] -eq "markdown") { "markdown" } else { "code" }
        $currentLines = [System.Collections.Generic.List[string]]::new()
        continue
    }
    $currentLines.Add($line)
}
Add-Block -CellType $currentType -CellLines $currentLines

$notebook = Get-Content -LiteralPath $NotebookPath -Raw | ConvertFrom-Json
$cells = foreach ($block in $blocks) {
    $cellLines = foreach ($line in $block.Lines) {
        $value = $line
        if ($block.Type -eq "markdown") {
            if ($line -eq '#') {
                $value = ''
            }
            elseif ($line.StartsWith('# ')) {
                $value = $line.Substring(2)
            }
            elseif ($line.StartsWith('#')) {
                $value = $line.Substring(1)
            }
        }
        "$value`n"
    }
    if ($block.Type -eq "code") {
        [pscustomobject]@{
            cell_type = "code"
            execution_count = $null
            metadata = [pscustomobject]@{}
            outputs = @()
            source = @($cellLines)
        }
    }
    else {
        [pscustomobject]@{
            cell_type = "markdown"
            metadata = [pscustomobject]@{}
            source = @($cellLines)
        }
    }
}

$notebook.cells = @($cells)
$json = $notebook | ConvertTo-Json -Depth 100
[System.IO.File]::WriteAllText(
    (Resolve-Path -LiteralPath $NotebookPath),
    $json + "`n",
    [System.Text.UTF8Encoding]::new($false)
)
