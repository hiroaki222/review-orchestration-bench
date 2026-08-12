#!/usr/bin/env bash
# Build the paper. PAPER_EMAIL env var (from .env at repo root) is injected into
# email.tex, which main.tex \input's — keeps the address out of source control.
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${PAPER_EMAIL:-}" ]; then
    ROOT_ENV="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.env"
    if [ -r "$ROOT_ENV" ]; then
        set -a; . "$ROOT_ENV"; set +a
    fi
fi
: "${PAPER_EMAIL:?PAPER_EMAIL is not set (define in .env at repo root)}"

printf '\\newcommand{\\authorEmail}{%s}\n' "$PAPER_EMAIL" > email.tex

export TEXINPUTS='../jsai_sig-1_0_0//:'
rm -f main.aux main.log main.dvi main.pdf main.bbl main.blg main.toc main.out main.fdb_latexmk main.fls main.synctex.gz
platex -kanji=utf8 -halt-on-error -interaction=nonstopmode main.tex
pbibtex main
platex -kanji=utf8 -halt-on-error -interaction=nonstopmode main.tex
platex -kanji=utf8 -halt-on-error -interaction=nonstopmode main.tex
dvipdfmx main.dvi

echo "built $(pwd)/main.pdf"
