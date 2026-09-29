param(
    [string]$Python = "python",
    [string]$Output = "output",
    [switch]$TablesOnly
)

# The released paper numbers use the audited NumPy dispatch path. Keep this
# setup in one entry point so the ordinary paper reproduction does not depend
# on the caller's CPU features or an implicit environment variable.
$previousFeatures = $env:NPY_DISABLE_CPU_FEATURES
$env:NPY_DISABLE_CPU_FEATURES = "AVX512F,AVX2"
Push-Location $PSScriptRoot
try {
    $analysisArgs = @("all", "--clean", "--output", $Output)
    if ($TablesOnly) {
        $analysisArgs += "--tables-only"
    }
    Write-Host "Paper reproduction: output=$Output"
    & $Python -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from agcs_analysis.yaw_comparison import validate_paper_environment; validate_paper_environment(); from agcs_analysis.cli import main; main()' $PSScriptRoot @analysisArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Paper reproduction failed with exit code $LASTEXITCODE"
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
