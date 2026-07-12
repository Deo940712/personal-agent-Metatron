param(
    [string]$Part,
    [string]$Slice,
    [switch]$IncludeDependencies,
    [switch]$All,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

if ($All -and ($Part -or $Slice)) {
    throw "Use -All without -Part or -Slice."
}

if ($Slice -and -not $Part) {
    throw "-Slice requires -Part."
}

if (-not $All -and -not $Part) {
    throw "Specify -All or -Part."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptBeaconManifest = Join-Path $scriptDir "manifest.json"
$repoBeaconManifest = Join-Path (Get-Location).Path ".beacon\verification\manifest.json"
$manifestPath = if (Test-Path -LiteralPath $scriptBeaconManifest) { $scriptBeaconManifest } else { $repoBeaconManifest }
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not $manifest.parts) {
    throw "Manifest must contain a 'parts' object."
}

$script:Failures = 0
$script:Visited = @{}

function Get-PropertyValue {
    param($Object, [string]$Name)
    $property = $Object.PSObject.Properties[$Name]
    if (-not $property) { return $null }
    return $property.Value
}

function Get-PropertyNames {
    param($Object)
    return @($Object.PSObject.Properties | ForEach-Object { $_.Name })
}

function Invoke-Slice {
    param(
        [string]$PartName,
        [string]$SliceName,
        [bool]$WithDependencies
    )

    $key = "$PartName/$SliceName"
    if ($script:Visited[$key]) { return }
    $script:Visited[$key] = $true

    $partNode = Get-PropertyValue -Object $manifest.parts -Name $PartName
    if (-not $partNode) { throw "Part not found in manifest: $PartName" }
    if (-not $partNode.slices) { throw "Part has no slices: $PartName" }

    $sliceNode = Get-PropertyValue -Object $partNode.slices -Name $SliceName
    if (-not $sliceNode) { throw "Slice not found in manifest: $PartName/$SliceName" }

    if ($WithDependencies -and $sliceNode.dependsOn) {
        foreach ($dependency in @($sliceNode.dependsOn)) {
            Invoke-Slice -PartName $PartName -SliceName $dependency -WithDependencies $true
        }
    }

    "== $PartName/$SliceName =="

    $commands = @($sliceNode.commands | Where-Object { $_ })
    $sliceType = if ($sliceNode.type) { [string]$sliceNode.type } else { "implementation" }

    if ($commands.Count -eq 0) {
        $message = "No automated commands declared for $PartName/$SliceName. UnitTestCore will not invent commands."
        if ($Strict -and $sliceType -ne "design") {
            $script:Failures += 1
            "FAIL: $message"
        } else {
            "WARN: $message"
        }
    }

    foreach ($command in $commands) {
        "> $command"
        & powershell -NoProfile -ExecutionPolicy Bypass -Command $command
        if ($LASTEXITCODE -ne 0) {
            $script:Failures += 1
            "FAIL: command exited with $LASTEXITCODE"
        } else {
            "PASS"
        }
    }

    $manualQa = @($sliceNode.manualQa | Where-Object { $_ })
    if ($manualQa.Count -gt 0) {
        "Manual QA (reported, not executed):"
        foreach ($item in $manualQa) {
            "- not-run: $item"
        }
    }
}

function Invoke-Part {
    param([string]$PartName)

    $partNode = Get-PropertyValue -Object $manifest.parts -Name $PartName
    if (-not $partNode) { throw "Part not found in manifest: $PartName" }
    if (-not $partNode.slices) { throw "Part has no slices: $PartName" }

    foreach ($sliceName in Get-PropertyNames -Object $partNode.slices) {
        Invoke-Slice -PartName $PartName -SliceName $sliceName -WithDependencies $false
    }
}

if ($All) {
    foreach ($partName in Get-PropertyNames -Object $manifest.parts) {
        Invoke-Part -PartName $partName
    }
} elseif ($Slice) {
    Invoke-Slice -PartName $Part -SliceName $Slice -WithDependencies ([bool]$IncludeDependencies)
} else {
    Invoke-Part -PartName $Part
}

if ($script:Failures -gt 0) {
    throw "UnitTestCore completed with $script:Failures failure(s)."
}

"UnitTestCore completed. Manual QA items above are reports only, not executed."
