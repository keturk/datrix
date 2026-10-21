# What each PowerShell file defines, read with PowerShell's own parser.
#
# Reads a JSON array of {path, text} on stdin and writes a JSON array on stdout, one entry per
# input file in the same order: {error, synopsis, symbols}. Each symbol is {name, qualname, kind,
# line, end_line, doc}. A file the parser reports errors for has an error and no symbols.
# Called by datrix_scripts.code_index.formats, which turns each entry into the index's file facts.

$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8

function New-Symbol {
    param(
        [string]$Name,
        [string]$Qualname,
        [string]$Kind,
        [System.Management.Automation.Language.IScriptExtent]$Extent,
        [string]$Doc,
        # The line that names the definition, when it is not the first line of its extent
        # (a parameter's attributes come before its name).
        [int]$NameLine = 0
    )
    [pscustomobject]@{
        name     = $Name
        qualname = $Qualname
        kind     = $Kind
        line     = if ($NameLine -gt 0) { $NameLine } else { $Extent.StartLineNumber }
        end_line = $Extent.EndLineNumber
        doc      = $Doc
    }
}

function Get-ParameterSymbols {
    param(
        [System.Management.Automation.Language.ParameterAst[]]$Parameters,
        [string]$Prefix,
        [System.Management.Automation.Language.CommentHelpInfo]$Help
    )
    foreach ($parameter in $Parameters) {
        $name = $parameter.Name.VariablePath.UserPath
        $doc = ''
        if ($null -ne $Help -and $Help.Parameters.ContainsKey($name.ToUpperInvariant())) {
            $doc = $Help.Parameters[$name.ToUpperInvariant()]
        }
        New-Symbol -Name $name -Qualname "$Prefix$name" -Kind 'parameter' -Extent $parameter.Extent -Doc $doc `
            -NameLine $parameter.Name.Extent.StartLineNumber
    }
}

function Get-FunctionSymbols {
    param([System.Management.Automation.Language.FunctionDefinitionAst]$Function)
    $help = $Function.GetHelpContent()
    $synopsis = if ($null -ne $help) { $help.Synopsis } else { '' }
    New-Symbol -Name $Function.Name -Qualname $Function.Name -Kind 'function' -Extent $Function.Extent -Doc $synopsis
    $parameters = @($Function.Parameters) + @($Function.Body.ParamBlock.Parameters) | Where-Object { $null -ne $_ }
    Get-ParameterSymbols -Parameters $parameters -Prefix "$($Function.Name)." -Help $help
}

function Get-FileOutline {
    param([string]$Path, [string]$Text)
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Text, $Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        $first = $errors[0]
        return [pscustomobject]@{
            error    = "ParseError: line $($first.Extent.StartLineNumber): $($first.Message)"
            synopsis = ''
            symbols  = @()
        }
    }
    $help = $ast.GetHelpContent()
    $symbols = [System.Collections.Generic.List[object]]::new()
    if ($null -ne $ast.ParamBlock) {
        foreach ($symbol in Get-ParameterSymbols -Parameters $ast.ParamBlock.Parameters -Prefix '' -Help $help) {
            $symbols.Add($symbol)
        }
    }
    $isFunction = { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }
    foreach ($function in $ast.FindAll($isFunction, $true)) {
        foreach ($symbol in Get-FunctionSymbols -Function $function) {
            $symbols.Add($symbol)
        }
    }
    [pscustomobject]@{
        error    = ''
        synopsis = if ($null -ne $help) { $help.Synopsis } else { '' }
        symbols  = $symbols.ToArray()
    }
}

$files = @([Console]::In.ReadToEnd() | ConvertFrom-Json)
$outlines = foreach ($file in $files) { Get-FileOutline -Path $file.path -Text $file.text }
ConvertTo-Json -InputObject @($outlines) -Depth 5 -Compress
