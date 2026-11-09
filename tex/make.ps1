# Build every figure before compiling the paper. Run from any working directory.
$ErrorActionPreference = 'Stop'

Push-Location -LiteralPath $PSScriptRoot
try {
    $figureDirectories = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figures') -Directory |
        Sort-Object Name

    foreach ($figureDirectory in $figureDirectories) {
        $figureScript = Join-Path $figureDirectory.FullName 'make.ps1'
        if (-not (Test-Path -LiteralPath $figureScript -PathType Leaf)) {
            throw "Missing figure build script: $figureScript"
        }

        Write-Host "Building figure: $($figureDirectory.Name)"
        $LASTEXITCODE = 0
        & $figureScript
        if ($LASTEXITCODE -ne 0) {
            throw "Figure build failed: $($figureDirectory.Name) (exit code: $LASTEXITCODE)."
        }
    }

    Write-Host 'Building main.tex'
    & latexmk -pdf '-outdir=.' -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 'main.tex'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build main.tex (latexmk exit code: $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
