# latexmk tracks input files and keeps the PDF and build cache in this directory.
$ErrorActionPreference = 'Stop'

Push-Location -LiteralPath $PSScriptRoot
try {
    & latexmk -pdf '-outdir=.' -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 'method-framework.tex'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build method-framework.tex (latexmk exit code: $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
