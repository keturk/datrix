<#
.SYNOPSIS
    Clone every Datrix repository into a workspace folder and link the workspace's .claude folder.

.DESCRIPTION
    Clones each Datrix repo from https://github.com/<Owner>/<repo>.git into <Workspace>\<repo>,
    then creates <Workspace>\.claude as a symbolic link to <Workspace>\datrix\claude-config\.claude.

    A repo folder that already holds a clone of the same remote is left as it is. A folder that
    exists but is not that clone is reported and left untouched. An existing .claude that is not
    the expected link is reported and left untouched. Exits 1 when anything failed.

    Creating a symbolic link on Windows needs Developer Mode on, or an elevated (Administrator) shell.
    Without either, the script asks for elevation (a UAC prompt) for the link step alone.

.PARAMETER Workspace
    Folder to clone into. Default: the folder this script is in.

.PARAMETER Owner
    GitHub account that owns the repos. Default: keturk.

.PARAMETER DryRun
    Print what would be done and change nothing.

.EXAMPLE
    .\clone-all.ps1
    .\clone-all.ps1 -Workspace D:\datrix
    .\clone-all.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$Workspace = $PSScriptRoot,
    [string]$Owner = 'keturk',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Keep in step with .claude/docs/repo-boundaries.md ("The package repos").
$Repos = @(
    'datrix',
    'datrix-cli',
    'datrix-codegen-angular',
    'datrix-codegen-aws',
    'datrix-codegen-azure',
    'datrix-codegen-common',
    'datrix-codegen-component',
    'datrix-codegen-docker',
    'datrix-codegen-flutter',
    'datrix-codegen-kernel',
    'datrix-codegen-python',
    'datrix-codegen-sql',
    'datrix-codegen-typescript',
    'datrix-codegen-typescript-core',
    'datrix-common',
    'datrix-extensions',
    'datrix-language',
    'datrix-rdbms-schema',
    'datrix-semantic',
    'datrix-testing',
    'datrix-vscode'
)

function Get-NormalizedUrl([string]$Url) {
    return $Url.Trim().TrimEnd('/') -replace '\.git$', ''
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host 'git is not on PATH. Install Git for Windows (https://git-scm.com) and run this again.' -ForegroundColor Red
    exit 1
}

$Workspace = [System.IO.Path]::GetFullPath($Workspace)
if (-not (Test-Path -LiteralPath $Workspace)) {
    if ($DryRun) {
        Write-Host "[dry-run] would create $Workspace"
    } else {
        New-Item -ItemType Directory -Path $Workspace | Out-Null
    }
}

$cloned = @()
$present = @()
$failed = @()

foreach ($repo in $Repos) {
    $url = "https://github.com/$Owner/$repo.git"
    $dir = Join-Path $Workspace $repo

    if (Test-Path -LiteralPath $dir) {
        if (-not (Test-Path -LiteralPath (Join-Path $dir '.git'))) {
            $failed += "$repo - $dir exists but is not a git repository; left untouched"
            continue
        }
        $origin = git -C $dir remote get-url origin 2>&1
        if ($LASTEXITCODE -ne 0) {
            $failed += "$repo - $dir has no 'origin' remote ($origin); left untouched"
            continue
        }
        if ((Get-NormalizedUrl $origin) -ne (Get-NormalizedUrl $url)) {
            $failed += "$repo - $dir is a clone of $origin, not $url; left untouched"
            continue
        }
        Write-Host "present  $repo"
        $present += $repo
        continue
    }

    if ($DryRun) {
        Write-Host "[dry-run] git clone -c core.longpaths=true $url $dir"
        $cloned += $repo
        continue
    }

    Write-Host "cloning  $repo" -ForegroundColor Cyan
    git clone -c core.longpaths=true $url $dir
    if ($LASTEXITCODE -ne 0) {
        $failed += "$repo - git clone $url exited $LASTEXITCODE"
        continue
    }
    $cloned += $repo
}

# <Workspace>\.claude -> <Workspace>\datrix\claude-config\.claude
$link = Join-Path $Workspace '.claude'
$target = Join-Path $Workspace 'datrix\claude-config\.claude'
$linkState = ''

$existing = Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
if ($existing) {
    $existingTarget = @($existing.Target)[0]
    if ($existing.LinkType -eq 'SymbolicLink' -and $existingTarget -and
        ([System.IO.Path]::GetFullPath($existingTarget).TrimEnd('\') -eq $target.TrimEnd('\'))) {
        Write-Host "present  .claude -> $target"
        $linkState = 'present'
    } else {
        $failed += ".claude - $link already exists and is not a symbolic link to $target; left untouched"
    }
} elseif ($DryRun) {
    Write-Host "[dry-run] New-Item -ItemType SymbolicLink -Path $link -Target $target"
    $linkState = 'would create'
} elseif (-not (Test-Path -LiteralPath $target)) {
    $failed += ".claude - link target $target does not exist (did the datrix clone fail?)"
} else {
    $linkCommand = "New-Item -ItemType SymbolicLink -Path '{0}' -Target '{1}' -ErrorAction Stop | Out-Null" -f
        ($link -replace "'", "''"), ($target -replace "'", "''")
    try {
        Invoke-Expression $linkCommand
    } catch {
        # Without Developer Mode a symbolic link needs an elevated shell: create just the link
        # in one, behind a UAC prompt.
        Write-Host "Creating .claude needs administrator rights here ($($_.Exception.Message)); asking for elevation..." -ForegroundColor Yellow
        $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($linkCommand))
        try {
            Start-Process -FilePath (Get-Process -Id $PID).Path -Verb RunAs -Wait `
                -ArgumentList '-NoProfile', '-EncodedCommand', $encoded
        } catch {
            Write-Host "Elevation failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    $made = Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
    if ($made -and $made.LinkType -eq 'SymbolicLink') {
        Write-Host "linked   .claude -> $target" -ForegroundColor Cyan
        $linkState = 'created'
    } else {
        $failed += ".claude - the symbolic link $link was not created. Turn on Developer Mode " +
            '(Settings > System > For developers) or run this script from an elevated shell, then run it again'
    }
}

Write-Host ''
$verb = if ($DryRun) { 'Would clone' } else { 'Cloned' }
Write-Host ("{0}: {1}   Already present: {2}   Failed: {3}" -f $verb, $cloned.Count, $present.Count, $failed.Count)
if ($linkState) { Write-Host ".claude link: $linkState" }
if ($failed.Count -gt 0) {
    Write-Host ''
    Write-Host 'Failures:' -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
exit 0
