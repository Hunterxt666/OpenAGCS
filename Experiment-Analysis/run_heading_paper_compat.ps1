param(
    [string]$Python = "python",
    [string]$Output = "",
    [ValidateSet("held-out", "legacy-paper")]
    [string]$Protocol = "held-out",
    [switch]$Figures
)

if (-not $Output) {
    $Output = if ($Protocol -eq "legacy-paper") { "output/heading_legacy_paper_compat" } else { "output/heading_held_out_paper_compat" }
}

# Retain the Comment 3.5 preprocessing path for both evaluation protocols.
$previousFeatures = $env:NPY_DISABLE_CPU_FEATURES
$env:NPY_DISABLE_CPU_FEATURES = "AVX512F,AVX2"
Push-Location $PSScriptRoot
try {
    $analysisArgs = @("heading", "--heading-protocol", $Protocol, "--output", $Output)
    if (-not $Figures) { $analysisArgs += "--tables-only" }
    Write-Host "Heading protocol: $Protocol; AKF parameters fixed; output: $Output"
    & $Python -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from agcs_analysis.yaw_comparison import validate_paper_environment; validate_paper_environment(); from agcs_analysis.cli import main; main()' $PSScriptRoot @analysisArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Heading reproduction failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    if ($null -eq $previousFeatures) {
        Remove-Item Env:NPY_DISABLE_CPU_FEATURES -ErrorAction SilentlyContinue
    }
    else {
        $env:NPY_DISABLE_CPU_FEATURES = $previousFeatures
    }
}
