[CmdletBinding()]
param(
    [switch]$CheckRemote
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$readmePath = Join-Path $repoRoot 'README.md'
$errors = [System.Collections.Generic.List[string]]::new()

Write-Host 'Validating structured data and SVG XML...'
Get-Content -Raw (Join-Path $repoRoot 'data/profile.json') | ConvertFrom-Json | Out-Null
Get-ChildItem (Join-Path $repoRoot 'assets') -Recurse -Filter '*.svg' | ForEach-Object {
    try {
        [xml]$svg = Get-Content -Raw $_.FullName
        # The last-known-good file is an immutable snapshot of the supplied remote card.
        # Its enclosing README image supplies the accessible alternative text.
        if ($_.Name -ne 'streak-last-good.svg') {
            if ($svg.DocumentElement.GetAttribute('role') -ne 'img') { $errors.Add("SVG is missing role=img: $($_.FullName)") }
            if (-not $svg.SelectSingleNode("/*[local-name()='svg']/*[local-name()='title']")) { $errors.Add("SVG is missing title: $($_.FullName)") }
            if (-not $svg.SelectSingleNode("/*[local-name()='svg']/*[local-name()='desc']")) { $errors.Add("SVG is missing description: $($_.FullName)") }
        }
    }
    catch { $errors.Add("Invalid SVG XML: $($_.FullName) -- $($_.Exception.Message)") }
}

Write-Host 'Checking README local asset references...'
$readme = Get-Content -Raw $readmePath
$profile = Get-Content -Raw (Join-Path $repoRoot 'data/profile.json') | ConvertFrom-Json
$streakUrl = $profile.githubActivity.streakPrimaryUrl
$startMarker = '<!-- streak:start -->'
$endMarker = '<!-- streak:end -->'
$startCount = ([regex]::Matches($readme, [regex]::Escape($startMarker))).Count
$endCount = ([regex]::Matches($readme, [regex]::Escape($endMarker))).Count
if ($startCount -ne 1 -or $endCount -ne 1) {
    $errors.Add("README must contain exactly one streak marker pair (found start=$startCount, end=$endCount)")
} else {
    $streakPattern = [regex]::Escape($startMarker) + '(?s).*?' + [regex]::Escape($endMarker)
    $streakBlock = [regex]::Match($readme, $streakPattern).Value
    $allowedStreakSources = @(
        $streakUrl,
        './assets/generated/streak-last-good.svg',
        './assets/generated/streak-fallback.svg'
    )
    if (-not ($allowedStreakSources | Where-Object { $streakBlock.Contains($_) })) {
        $errors.Add('README streak block does not reference the canonical live URL or an approved local fallback')
    }
}
$imagesWithoutAlt = [regex]::Matches($readme, '<img\b(?![^>]*\balt=)[^>]*>', 'IgnoreCase')
if ($imagesWithoutAlt.Count) { $errors.Add("README contains $($imagesWithoutAlt.Count) image tag(s) without alt text") }
$localRefs = [regex]::Matches($readme, '(?:src|srcset)="(\./[^"]+)"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
foreach ($ref in $localRefs) {
    $relative = $ref.TrimStart('.', '/') -replace '/', [IO.Path]::DirectorySeparatorChar
    $target = Join-Path $repoRoot $relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { $errors.Add("Missing local asset: $ref") }
}

if ($CheckRemote) {
    Write-Host 'Checking remote HTTP links (redirects allowed)...'
    $urls = [regex]::Matches($readme, 'https://[^\s\)\"]+') | ForEach-Object { $_.Value.TrimEnd('/', '.', ',') } | Sort-Object -Unique
    foreach ($url in $urls) {
        try {
            $response = Invoke-WebRequest -Uri $url -Method Head -MaximumRedirection 8 -TimeoutSec 20 -UseBasicParsing
            Write-Host ("{0}  {1}" -f $response.StatusCode, $url)
        } catch {
            try {
                $response = Invoke-WebRequest -Uri $url -Method Get -MaximumRedirection 8 -TimeoutSec 20 -UseBasicParsing
                Write-Host ("{0}  {1}" -f $response.StatusCode, $url)
            } catch {
                $statusCode = 0
                if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                    $statusCode = [int]$_.Exception.Response.StatusCode
                }
                if ($statusCode -in 401, 403, 999) {
                    Write-Warning ("{0}  {1} (reachable but blocks automated checks)" -f $statusCode, $url)
                } else {
                    $errors.Add("Remote link failed: $url -- $($_.Exception.Message)")
                }
            }
        }
    }
}

if ($errors.Count) {
    $errors | ForEach-Object { Write-Host "ERROR: $_" -ForegroundColor Red }
    exit 1
}

Write-Host ("OK: {0} local assets referenced; {1} SVG files valid." -f $localRefs.Count, (Get-ChildItem (Join-Path $repoRoot 'assets') -Recurse -Filter '*.svg').Count)
