<#
.SYNOPSIS
    Exports all code files (including .txt) from the repository to a single file, respecting .gitignore patterns on Windows.
.DESCRIPTION
    - Reads .gitignore and escapes and normalizes patterns to match both '/' and '\\'.
    - Excludes files matching gitignore unless explicitly included.
    - Skips the .git directory entirely.
    - Includes .txt files by default (unless in .gitignore).
    - Always forces-includes specific paths (e.g., config/config.yaml).
#>

param(
    [string]$scriptDirectory,
    [string]$outputFile = "all_code.txt"
)

# Determine script directory if not provided
if (-not $scriptDirectory) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
}
# Resolve output path
$resolved = Resolve-Path -Path $outputFile -ErrorAction SilentlyContinue
if ($resolved) { $outputFile = $resolved.Path } else { $outputFile = Join-Path $scriptDirectory $outputFile }

# Read, escape, and normalize .gitignore patterns
$gitignorePath = Join-Path $scriptDirectory ".gitignore"
$exclusions = @()
if (Test-Path $gitignorePath) {
    Get-Content $gitignorePath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            # Strip trailing slash
            $raw = $line.TrimEnd('/')
            # Escape regex metacharacters
            $esc = [regex]::Escape($raw)
            # Restore wildcard semantics
            $esc = $esc -replace '\\\*', '.*' -replace '\\\?', '.'
            # Allow slashes to match either dir separator
            $pattern = $esc -replace '/', '[\\/]'
            # Match anywhere in relative path
            $pattern = ".*$pattern.*"
            $exclusions += $pattern
        }
    }
}

# Explicitly include files even if gitignored
$includedFiles = @('config/config.yaml')

# Initialize or clear the output file
if (Test-Path $outputFile) { Remove-Item $outputFile -Force }
New-Item -Path $outputFile -ItemType File -Force | Out-Null

# Traverse and export
Get-ChildItem -Path $scriptDirectory -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($scriptDirectory.Length + 1).TrimStart('\', '/')

    # Skip anything in .git directory explicitly
    if ($relative -match '^(\.git)[\\/]') { return }

    $skip = $false
    # Check against exclusions
    foreach ($pat in $exclusions) {
        if ($relative -match $pat) {
            $skip = $true; break
        }
    }
    # Override skip if explicitly included
    if ($includedFiles -contains $relative) { $skip = $false }

    if (-not $skip) {
        Add-Content -Path $outputFile -Value "`n`n=== $relative ===`n`n"
        Get-Content -Path $_.FullName | Add-Content -Path $outputFile
        Write-Host "Processed: $relative"
    }
}

Write-Host "Export complete. Output file: $outputFile"
