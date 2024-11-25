# Define the output file (set to the same folder the script is in)
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputFile = Join-Path -Path $scriptDirectory -ChildPath "all_code.txt"

# Remove the file if it already exists to avoid appending to an old version
if (Test-Path $outputFile) { 
    Remove-Item $outputFile 
}

# Parse .gitignore to build an exclusion list
$gitignorePath = Join-Path -Path $scriptDirectory -ChildPath ".gitignore"
$exclusions = @()
if (Test-Path $gitignorePath) {
    $gitignore = Get-Content -Path $gitignorePath -ErrorAction SilentlyContinue
    $exclusions = $gitignore | ForEach-Object { $_.Trim() } | Where-Object { 
        $_ -notmatch '^#' -and $_ -ne '' 
    }
}

# Recursively get all files, process each one while following .gitignore rules
Get-ChildItem -Path $scriptDirectory -Recurse -File | ForEach-Object {
    # Skip files if they match any .gitignore exclusion pattern or are in __pycache__ folders
    $skipFile = $false
    foreach ($exclusion in $exclusions) {
        # Handle wildcard patterns in .gitignore
        $pattern = [regex]::Escape($exclusion).Replace('\*', '.*').Replace('\?', '.')
        if ($_.FullName -match $pattern -or $_.DirectoryName -match '__pycache__') {
            $skipFile = $true
            break
        }
    }
    
    # Additional checks to skip specific files
    if ($_.Name -in @('bot.log', 'package-lock.json', 'package.json', 'TESTDatabase.db')) {
        $skipFile = $true
    }
    
    if (-not $skipFile) {
        # Append the file name as a header
        Add-Content -Path $outputFile -Value "`n`n=== $($_.FullName) ===`n`n"
        # Append the content of the file
        Get-Content -Path $_.FullName | Add-Content -Path $outputFile
        Write-Host "Processed file: $($_.FullName)"
    }
}

Write-Host "Script completed. Output file created at: $outputFile"
