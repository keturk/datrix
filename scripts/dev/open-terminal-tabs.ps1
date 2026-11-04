# Opens one new Windows Terminal window with five PowerShell 7 tabs, all starting in the Datrix
# workspace. Launched from the taskbar shortcut.

$ErrorActionPreference = 'Stop'

# This script lives in <workspace>\datrix\scripts\dev.
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$terminalProfile = 'PowerShell'
$tabCount = 5

$newTab = @('new-tab', '--profile', $terminalProfile, '--startingDirectory', $workspace)
$wtArguments = @('--window', 'new') + $newTab
foreach ($tab in 2..$tabCount) {
    $wtArguments += @(';') + $newTab
}
$wtArguments += @(';', 'focus-tab', '--target', '0')

& wt.exe @wtArguments
