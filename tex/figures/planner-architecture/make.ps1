# latexmk tracks input files and keeps the PDF and build cache in this directory.
$ErrorActionPreference = 'Stop'

Push-Location -LiteralPath $PSScriptRoot
try {
    & latexmk -pdf '-outdir=.' -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 'planner-architecture.tex'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build planner-architecture.tex (latexmk exit code: $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
