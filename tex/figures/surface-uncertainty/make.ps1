# latexmk tracks input files and keeps the PDF and build cache in this directory.
$ErrorActionPreference = 'Stop'

Push-Location -LiteralPath $PSScriptRoot
try {
    & latexmk -pdf '-outdir=.' -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 'spc-model-uncertainty.tex'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build spc-model-uncertainty.tex (latexmk exit code: $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
