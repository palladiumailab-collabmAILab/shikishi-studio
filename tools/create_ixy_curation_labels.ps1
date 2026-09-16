param(
    [string]$DatasetRoot = 'C:\Users\palla\Documents\shikishi-artifacts\prepared-datasets\ixy_style\1_ixy_style'
)

$ErrorActionPreference = 'Stop'

function Has-Tag([string[]]$Tags, [string]$Tag) {
    return $Tags -contains $Tag
}

$images = @{}
Get-ChildItem -LiteralPath $DatasetRoot -File |
    Where-Object { $_.Extension.ToLowerInvariant() -in @('.jpg', '.png', '.webp') } |
    ForEach-Object { $images[$_.BaseName] = $_.Name }

$labels = foreach ($caption in Get-ChildItem -LiteralPath $DatasetRoot -Filter '*.txt' -File | Sort-Object Name) {
    if (-not $images.ContainsKey($caption.BaseName)) {
        throw "Image missing for $($caption.Name)"
    }
    $tags = @((Get-Content -LiteralPath $caption.FullName -Raw).Trim() -split '\s*,\s*' | Where-Object { $_ })
    $isGroup = (Has-Tag $tags 'multiple_girls') -or (Has-Tag $tags '2girls') -or (Has-Tag $tags '3girls') -or (Has-Tag $tags '1boy')
    $isSimple = Has-Tag $tags 'simple_background'
    $isWhite = Has-Tag $tags 'white_background'
    $isPortrait = Has-Tag $tags 'upper_body'
    $isMedium = Has-Tag $tags 'cowboy_shot'
    $isFull = Has-Tag $tags 'full_body'
    $isVariant = (Has-Tag $tags 'chibi') -or (Has-Tag $tags 'sketch') -or (Has-Tag $tags 'comic')
    $sourceDuplicate = (Has-Tag $tags 'duplicate') -or (Has-Tag $tags 'pixel-perfect_duplicate')
    $metadataNoise = (Has-Tag $tags 'bad_id') -or (Has-Tag $tags 'bad_pixiv_id')

    $subject = if ($isGroup) { 'group_or_male' } elseif (Has-Tag $tags '1girl') { 'single_female' } else { 'other' }
    $background = if ($isWhite) { 'simple_white' } elseif ($isSimple) { 'simple_colored' } else { 'detailed_or_unspecified' }
    $framing = if ($isPortrait) { 'upper_body' } elseif ($isMedium) { 'cowboy_shot' } elseif ($isFull) { 'full_body' } else { 'other' }
    $archetype = if ($isVariant) { 'variant_style' }
        elseif ($isGroup) { 'group_or_male' }
        elseif ($isWhite -and $isPortrait) { 'white_bg_portrait' }
        elseif ($isSimple -and $isPortrait) { 'simple_bg_portrait' }
        elseif ($isSimple) { 'simple_bg_character' }
        elseif ($isPortrait) { 'detailed_bg_portrait' }
        else { 'detailed_bg_character' }
    $recommendation = if ($sourceDuplicate) { 'review_source_duplicate' } else { 'core_candidate' }

    [pscustomobject]@{
        image = $images[$caption.BaseName]
        caption = $caption.Name
        archetype = $archetype
        subject = $subject
        background = $background
        framing = $framing
        school_uniform = (Has-Tag $tags 'school_uniform')
        source_duplicate_flag = $sourceDuplicate
        metadata_noise_flag = $metadataNoise
        recommendation = $recommendation
    }
}

$labels | Export-Csv -LiteralPath (Join-Path $DatasetRoot 'curation_labels.csv') -NoTypeInformation -Encoding utf8
$summary = [ordered]@{
    total_images = $labels.Count
    archetypes = @($labels | Group-Object archetype | Sort-Object Name | ForEach-Object { [pscustomobject]@{ label = $_.Name; count = $_.Count } })
    recommendations = @($labels | Group-Object recommendation | Sort-Object Name | ForEach-Object { [pscustomobject]@{ label = $_.Name; count = $_.Count } })
}
$summary | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $DatasetRoot 'curation_summary.json') -Encoding utf8

Write-Output "Created $(Join-Path $DatasetRoot 'curation_labels.csv')"
$summary | ConvertTo-Json -Depth 4
