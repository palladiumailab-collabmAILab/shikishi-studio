#requires -Version 5.1

<##
.SYNOPSIS
  Import image and video files from an unlocked ROG Phone over Windows MTP.

.DESCRIPTION
  The phone remains the source of truth. Files are copied through a temporary
  local directory, hashed, and then moved into the external artifact area.
  The watcher never deletes or moves files on the phone.
#>

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Once,
    [switch]$DryRun,
    [string]$DestinationRoot,
    [ValidateRange(5, 3600)]
    [int]$IntervalSeconds = 15,
    [ValidateRange(10, 3600)]
    [int]$WaitTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "Shikishi ROG Phone Media Import"
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:SHIKISHI_ARTIFACTS_ROOT)) {
        $DestinationRoot = Join-Path $env:USERPROFILE "Documents\shikishi-artifacts\rog-phone-media"
    } else {
        $DestinationRoot = Join-Path $env:SHIKISHI_ARTIFACTS_ROOT "rog-phone-media"
    }
}
$DestinationRoot = [IO.Path]::GetFullPath($DestinationRoot)
$transferRoot = Join-Path $DestinationRoot ".transfers"
$statePath = Join-Path $DestinationRoot "import-state.jsonl"
$logPath = Join-Path $DestinationRoot "import-log.jsonl"

if ($Install -and $Uninstall) {
    throw "-Install and -Uninstall cannot be used together."
}

New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
New-Item -ItemType Directory -Path $transferRoot -Force | Out-Null

function Write-JsonLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [hashtable]$Record
    )

    $json = $Record | ConvertTo-Json -Compress -Depth 8
    Add-Content -LiteralPath $Path -Value $json -Encoding UTF8
}

function Write-ImportLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Event,
        [string]$Message,
        [hashtable]$Data = @{}
    )

    $record = @{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        event     = $Event
        message   = $Message
    }
    foreach ($key in $Data.Keys) {
        $record[$key] = $Data[$key]
    }
    Write-JsonLine -Path $logPath -Record $record
    Write-Verbose ("{0}: {1}" -f $Event, $Message)
}

function Get-ImportedSourceKeys {
    $keys = @{}
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return $keys
    }

    foreach ($line in Get-Content -LiteralPath $statePath) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $entry = $line | ConvertFrom-Json
            if ($null -ne $entry.source_key) {
                $keys[[string]$entry.source_key] = $true
            }
        } catch {
            Write-ImportLog -Event "state-invalid" -Message "Ignoring malformed import state line." -Data @{
                error = $_.Exception.Message
            }
        }
    }
    return $keys
}

function Test-MediaFile {
    param([Parameter(Mandatory = $true)][string]$Name)

    $extension = [IO.Path]::GetExtension($Name).ToLowerInvariant()
    return @(
        ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
        ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp"
    ) -contains $extension
}

function Test-SafeRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    if ([IO.Path]::IsPathRooted($RelativePath)) {
        return $false
    }
    foreach ($part in ($RelativePath -split "[\\/]")) {
        if ([string]::IsNullOrWhiteSpace($part) -or $part -eq "." -or $part -eq "..") {
            return $false
        }
    }
    return $true
}

function Get-ChildFolder {
    param(
        [Parameter(Mandatory = $true)]$Folder,
        [Parameter(Mandatory = $true)][string]$Name
    )

    foreach ($item in @($Folder.Items())) {
        if ([string]$item.Name -ieq $Name -and $item.IsFolder) {
            return $item.GetFolder
        }
    }
    return $null
}

function Get-RemoteMediaFiles {
    param(
        [Parameter(Mandatory = $true)]$Folder,
        [Parameter(Mandatory = $true)][string]$RelativeRoot
    )

    foreach ($item in @($Folder.Items())) {
        $name = [string]$item.Name
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        $relativePath = Join-Path $RelativeRoot $name
        if ($item.IsFolder) {
            $child = $item.GetFolder
            if ($null -ne $child) {
                Get-RemoteMediaFiles -Folder $child -RelativeRoot $relativePath
            }
        } elseif (Test-MediaFile -Name $name) {
            $size = 0L
            try {
                $size = [int64]$item.Size
            } catch {
                $size = 0L
            }
            [pscustomobject]@{
                Item         = $item
                RelativePath = $relativePath
                Size         = $size
                Modified     = [string]$item.ModifyDate
            }
        }
    }
}

function Get-RogPhoneFolder {
    try {
        $shell = New-Object -ComObject Shell.Application
        $computer = $shell.NameSpace(17)
        if ($null -eq $computer) {
            return $null
        }
        foreach ($item in @($computer.Items())) {
            if ([string]$item.Name -match "(?i)ROG\s*Phone") {
                return $item.GetFolder
            }
        }
    } catch {
        Write-ImportLog -Event "detection-failed" -Message "Windows Shell MTP detection failed." -Data @{
            error = $_.Exception.Message
        }
    }
    return $null
}

function Test-RogPhoneReady {
    param([Parameter(Mandatory = $true)]$PhoneFolder)

    foreach ($rootName in @("DCIM", "Pictures", "Movies")) {
        if ($null -ne (Get-ChildFolder -Folder $PhoneFolder -Name $rootName)) {
            return $true
        }
    }
    return $false
}

function Wait-ForStableFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    $deadline = (Get-Date).AddSeconds($WaitTimeoutSeconds)
    $previousLength = -1L
    $stableReads = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            $length = (Get-Item -LiteralPath $Path).Length
            if ($length -gt 0 -and $length -eq $previousLength) {
                $stableReads++
            } else {
                $stableReads = 0
            }
            if ($stableReads -ge 2) {
                return
            }
            $previousLength = $length
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Timed out waiting for stable MTP transfer: $Path"
}

function Copy-RemoteMediaFile {
    param(
        [Parameter(Mandatory = $true)]$FileRecord,
        [Parameter(Mandatory = $true)][string]$SourceKey
    )

    $relativePath = [string]$FileRecord.RelativePath
    if (-not (Test-SafeRelativePath -RelativePath $relativePath)) {
        throw "Unsafe MTP relative path rejected: $relativePath"
    }

    $finalPath = Join-Path $DestinationRoot $relativePath
    $finalDirectory = Split-Path -Parent $finalPath
    New-Item -ItemType Directory -Path $finalDirectory -Force | Out-Null

    $transferDirectory = Join-Path $transferRoot ([guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $transferDirectory -Force | Out-Null
    try {
        $shell = New-Object -ComObject Shell.Application
        $destination = $shell.NameSpace($transferDirectory)
        if ($null -eq $destination) {
            throw "Unable to open temporary transfer directory: $transferDirectory"
        }
        $destination.CopyHere($FileRecord.Item, 0x514)
        $temporaryPath = Join-Path $transferDirectory ([string]$FileRecord.Item.Name)
        Wait-ForStableFile -Path $temporaryPath
        $hash = (Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash.ToLowerInvariant()

        $destinationPath = $finalPath
        if (Test-Path -LiteralPath $destinationPath -PathType Leaf) {
            $existingHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
            if ($existingHash -ieq $hash) {
                Write-ImportLog -Event "duplicate" -Message "Identical media already exists locally." -Data @{
                    source_key = $SourceKey
                    source_path = $relativePath
                    destination = $destinationPath
                    sha256      = $hash
                }
                Write-JsonLine -Path $statePath -Record @{
                    source_key       = $SourceKey
                    source_path      = $relativePath
                    source_sha256    = $hash
                    source_size      = [int64]$FileRecord.Size
                    source_modified  = [string]$FileRecord.Modified
                    destination      = $destinationPath
                    imported_at      = (Get-Date).ToUniversalTime().ToString("o")
                    duplicate        = $true
                }
                return
            }
            $base = [IO.Path]::GetFileNameWithoutExtension($destinationPath)
            $extension = [IO.Path]::GetExtension($destinationPath)
            $destinationPath = Join-Path $finalDirectory ("{0}-{1}{2}" -f $base, $hash.Substring(0, 12), $extension)
        }

        Move-Item -LiteralPath $temporaryPath -Destination $destinationPath
        Write-JsonLine -Path $statePath -Record @{
            source_key       = $SourceKey
            source_path      = $relativePath
            source_sha256    = $hash
            source_size      = [int64]$FileRecord.Size
            source_modified  = [string]$FileRecord.Modified
            destination      = $destinationPath
            imported_at      = (Get-Date).ToUniversalTime().ToString("o")
        }
        Write-ImportLog -Event "import-completed" -Message "Media imported from ROG Phone." -Data @{
            source_key = $SourceKey
            source_path = $relativePath
            destination = $destinationPath
            sha256 = $hash
        }
    } finally {
        if (Test-Path -LiteralPath $transferDirectory) {
            Remove-Item -LiteralPath $transferDirectory -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ImportPass {
    param([Parameter(Mandatory = $true)]$PhoneFolder)

    $importedKeys = Get-ImportedSourceKeys
    foreach ($rootName in @("DCIM", "Pictures", "Movies")) {
        $rootFolder = Get-ChildFolder -Folder $PhoneFolder -Name $rootName
        if ($null -eq $rootFolder) {
            continue
        }
        foreach ($file in @(Get-RemoteMediaFiles -Folder $rootFolder -RelativeRoot $rootName)) {
            $sourceKey = "{0}|{1}|{2}" -f $file.RelativePath, $file.Size, $file.Modified
            if ($importedKeys.ContainsKey($sourceKey)) {
                continue
            }
            try {
                if ($DryRun) {
                    Write-ImportLog -Event "dry-run" -Message "Media would be imported from ROG Phone." -Data @{
                        source_key = $sourceKey
                        source_path = [string]$file.RelativePath
                        source_size = [int64]$file.Size
                    }
                    $importedKeys[$sourceKey] = $true
                    continue
                }
                Copy-RemoteMediaFile -FileRecord $file -SourceKey $sourceKey
                $importedKeys[$sourceKey] = $true
            } catch {
                Write-ImportLog -Event "import-failed" -Message "Media import failed; source was preserved." -Data @{
                    source_key = $sourceKey
                    source_path = [string]$file.RelativePath
                    error = $_.Exception.Message
                }
            }
        }
    }
}

function Install-WatcherTask {
    $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -DestinationRoot "{1}"' -f $scriptPath, $DestinationRoot
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Import ROG Phone media for Shikishi Studio without deleting source files." -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-ImportLog -Event "task-installed" -Message "ROG Phone media watcher task registered and started." -Data @{
        task_name = $taskName
        script = $scriptPath
    }
}

function Uninstall-WatcherTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Write-ImportLog -Event "task-uninstalled" -Message "ROG Phone media watcher task removed." -Data @{
        task_name = $taskName
    }
}

if ($Install) {
    Install-WatcherTask
    exit 0
}
if ($Uninstall) {
    Uninstall-WatcherTask
    exit 0
}

$wasConnected = $false
$notReadyLogged = $false
do {
    $phoneFolder = Get-RogPhoneFolder
    $phoneReady = $null -ne $phoneFolder -and (Test-RogPhoneReady -PhoneFolder $phoneFolder)
    if (-not $phoneReady) {
        if ($wasConnected) {
            Write-ImportLog -Event "disconnected" -Message "ROG Phone is no longer available over MTP."
        } elseif (-not $notReadyLogged) {
            Write-ImportLog -Event "not-ready" -Message "ROG Phone is not detected or is not ready for file transfer."
            $notReadyLogged = $true
        }
        $wasConnected = $false
    } else {
        if (-not $wasConnected) {
            Write-ImportLog -Event "connected" -Message "ROG Phone detected over MTP."
        }
        $notReadyLogged = $false
        Invoke-ImportPass -PhoneFolder $phoneFolder
        $wasConnected = $true
    }

    if ($Once) {
        break
    }
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
