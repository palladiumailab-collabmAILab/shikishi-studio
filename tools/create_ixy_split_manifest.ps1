param(
    [string]$DatasetRoot = 'C:\Users\palla\Documents\shikishi-artifacts\prepared-datasets\ixy_style\1_ixy_style',
    [int]$Seed = 20260821
)

$ErrorActionPreference = 'Stop'

$images = Get-ChildItem -LiteralPath $DatasetRoot -File |
    Where-Object { $_.Extension.ToLowerInvariant() -in @('.jpg', '.png', '.webp') } |
    Sort-Object Name

$records = foreach ($image in $images) {
    $captionPath = Join-Path $DatasetRoot ($image.BaseName + '.txt')
    if (-not (Test-Path -LiteralPath $captionPath)) {
        throw "Caption missing for $($image.Name)"
    }

    $tags = (Get-Content -LiteralPath $captionPath -Raw).Trim() -split '\s*,\s*' |
        Where-Object { $_ } |
        Sort-Object -Unique
    $hasBadId = ($tags -contains 'bad_id') -or ($tags -contains 'bad_pixiv_id')
    [pscustomobject]@{
        image       = $image.Name
        caption     = (Split-Path -Leaf $captionPath)
        format      = $image.Extension.TrimStart('.').ToLowerInvariant()
        has_bad_id  = $hasBadId
        tag_count   = $tags.Count
        tag_set_key = ($tags -join ',')
    }
}

# Keep identical tag sets together within each balancing stratum.  Including the
# stratum in the key prevents a cross-format caption collision from distorting
# the format/bad-ID proportions.
$groups = foreach ($tagGroup in ($records | Group-Object { ('{0}|bad_id={1}' -f $_.format, $_.has_bad_id.ToString().ToLowerInvariant()) + [char]31 + $_.tag_set_key })) {
    $first = $tagGroup.Group[0]
    [pscustomobject]@{
        records = $tagGroup.Group
        stratum = '{0}|bad_id={1}' -f $first.format, $first.has_bad_id.ToString().ToLowerInvariant()
        # Deterministic pseudo-random ordering; no dependence on filesystem order.
        order = [System.BitConverter]::ToUInt32(
            [System.Security.Cryptography.SHA256]::HashData(
                [System.Text.Encoding]::UTF8.GetBytes("$Seed|$($tagGroup.Name)")), 0)
    }
}

$assignments = [System.Collections.Generic.List[object]]::new()
foreach ($stratumGroup in ($groups | Group-Object stratum)) {
    $ordered = $stratumGroup.Group | Sort-Object order
    $total = ($ordered | ForEach-Object { $_.records.Count } | Measure-Object -Sum).Sum
    $trainTarget = [math]::Round($total * 0.80, 0, [MidpointRounding]::AwayFromZero)
    $validationTarget = [math]::Round($total * 0.10, 0, [MidpointRounding]::AwayFromZero)
    $train = 0; $validation = 0

    foreach ($group in $ordered) {
        $n = $group.records.Count
        if ($train -lt $trainTarget) { $split = 'train'; $train += $n }
        elseif ($validation -lt $validationTarget) { $split = 'validation'; $validation += $n }
        else { $split = 'test' }

        foreach ($record in $group.records) {
            $assignments.Add([pscustomobject]@{
                image = $record.image; caption = $record.caption; split = $split
                stratum = $group.stratum; format = $record.format
                has_bad_id = $record.has_bad_id; tag_count = $record.tag_count
            })
        }
    }
}

$manifestPath = Join-Path $DatasetRoot 'split_manifest.csv'
$summaryPath = Join-Path $DatasetRoot 'split_summary.json'
$assignments | Sort-Object split, image | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8

$summary = [ordered]@{
    seed = $Seed
    ratios = [ordered]@{ train = 0.80; validation = 0.10; test = 0.10 }
    total_images = $assignments.Count
    split_counts = [ordered]@{}
    strata = @()
}
foreach ($split in 'train', 'validation', 'test') {
    $summary.split_counts[$split] = @($assignments | Where-Object split -eq $split).Count
}
$summary.strata = $assignments | Group-Object stratum | Sort-Object Name | ForEach-Object {
    $entry = [ordered]@{ stratum = $_.Name; total = $_.Count; train = 0; validation = 0; test = 0 }
    foreach ($split in 'train', 'validation', 'test') {
        $entry[$split] = @($_.Group | Where-Object split -eq $split).Count
    }
    [pscustomobject]$entry
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryPath -Encoding utf8

Write-Output "Created $manifestPath"
Write-Output "Created $summaryPath"
$summary | ConvertTo-Json -Depth 5
