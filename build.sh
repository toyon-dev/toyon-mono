#!/bin/sh
# Build Toyon Mono. Clones Hack's sources into build/hack on first run, fetches DejaVu Sans Mono
# (the glyphs some picks copy in) into build/ref, makes a Python environment with fontmake in
# build/env (uv), then runs tools/forge.py, which writes fonts/.
#
#     ./build.sh              both weights
#     ./build.sh Regular      one of Regular, Bold
set -e
ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"
if [ ! -d build/hack/source ]; then
    echo "==> cloning Hack"
    git clone --depth 1 --branch v3.003 https://github.com/source-foundry/Hack.git build/hack
fi
if [ ! -f build/ref/dejavu-sans-mono-bold.ttf ]; then
    echo "==> fetching DejaVu Sans Mono 2.37"
    mkdir -p build/ref/dl
    curl -sSL https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip -o build/ref/dl/dejavu.zip
    unzip -qo build/ref/dl/dejavu.zip -d build/ref/dl
    cp "$(find build/ref/dl -name DejaVuSansMono.ttf | head -1)" build/ref/dejavu-sans-mono.ttf
    cp "$(find build/ref/dl -name DejaVuSansMono-Bold.ttf | head -1)" build/ref/dejavu-sans-mono-bold.ttf
fi
if [ ! -x build/env/bin/python ]; then
    echo "==> python environment"
    uv venv build/env -q
    uv pip install -p build/env/bin/python -q fontmake ufoLib2 fonttools brotli uharfbuzz
fi
echo "==> forging"
build/env/bin/python tools/forge.py "$@"
echo "==> done"
