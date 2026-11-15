"""Draw specimen.svg, the picture at the top of the README.

    build/env/bin/python tools/specimen.py

Every letter in the picture is an outline taken from the built fonts and shaped with HarfBuzz,
so the ligatures, the kerns and the contextual t are the font's own, and the file needs no font
installed to show right. The comparison rows read Hack from build/hack, which build.sh clones.
"""

import re
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = {
    "r": ROOT / "fonts/ToyonMono-Regular.ttf",
    "b": ROOT / "fonts/ToyonMono-Bold.ttf",
    "h": ROOT / "build/hack/build/ttf/Hack-Regular.ttf",
}
OUT = ROOT / "specimen.svg"

UPM = 2048
WIDTH = 1200
PAD = 56
LINE = 700  # the operator line, in font units

CODE = """\
// toyon mono: every operator on one line
fn settle(queue: &[Task], limit: usize) -> Result<usize> {
    let mut done = 0;
    for task in queue.iter().filter(|t| t.cost <= limit) {
        if task.id != 0 && task.weight >= 1.5 * BASE {
            done += task.run()? - 1;
        }
    }
    Ok(done)
}"""
KEYWORDS = re.compile(r"\b(fn|let|mut|for|in|if)\b")

OPERATORS = "<- {[(-=+*×÷)]} -> <= >= ≠ ||"
LETTERS = "0123 aceg fijklrt QN ?! \"'"

COLOURS = {
    # class: (light, dark)
    "bg": ("#fbfaf8", "#171615"),
    "edge": ("#e6e2da", "#2b2927"),
    "ink": ("#1f1d1a", "#e9e6e0"),
    "muted": ("#8a857c", "#7d786f"),
    "accent": ("#c2452d", "#e0694f"),
}


class Face:
    def __init__(self, key, path):
        self.key = key
        self.tt = TTFont(path)
        self.order = self.tt.getGlyphOrder()
        self.glyphs = self.tt.getGlyphSet()
        self.hb = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))
        self.used = set()

    def shape(self, text):
        """The glyphs of a run as (glyph id, x, y) in font units, and the run's advance."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "calt": True})
        out, pen = [], 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, pen + pos.x_offset, pos.y_offset))
            pen += pos.x_advance
        self.used.update(g for g, _, _ in out)
        return out, pen

    def defs(self):
        for gid in sorted(self.used):
            pen = SVGPathPen(self.glyphs)
            self.glyphs[self.order[gid]].draw(pen)
            d = pen.getCommands()
            if d:
                yield f'<path id="{self.key}{gid}" d="{d}"/>'


faces = {key: Face(key, path) for key, path in FONTS.items()}
body = []


def text(face, string, x, baseline, size, cls="ink"):
    """Set one run with its left edge at x, and return the x where it ends."""
    if not string:
        return x
    f = faces[face]
    scale = size / UPM
    glyphs, advance = f.shape(string)
    uses = "".join(
        f'<use href="#{f.key}{gid}" x="{gx}"' + (f' y="{gy}"' if gy else "") + "/>"
        for gid, gx, gy in glyphs
    )
    body.append(
        f'<g class="{cls}" transform="translate({x:.2f} {baseline:.2f}) scale({scale:.5f} {-scale:.5f})">{uses}</g>'
    )
    return x + advance * scale


def rule(x0, x1, y, cls="edge", width=1):
    body.append(f'<path class="{cls} stroke" stroke-width="{width}" d="M{x0:.2f} {y:.2f}H{x1:.2f}"/>')


y = PAD

# The name, in the Bold, with the two weights named beside it.
y += 62
end = text("b", "Toyon Mono", PAD, y, 76)
text("r", "Regular", end + 36, y - 30, 20, "muted")
text("b", "Bold", end + 36, y, 20, "muted")
y += 44
rule(PAD, WIDTH - PAD, y)

# A page of code: keywords in the Bold, the comment muted.
y += 26
size, leading = 25, 39
for line in CODE.split("\n"):
    y += leading
    if line.startswith("//"):
        text("r", line, PAD, y, size, "muted")
        continue
    x, at = PAD, 0
    for m in KEYWORDS.finditer(line):
        x = text("r", line[at : m.start()], x, y, size)
        x = text("b", m.group(), x, y, size, "accent")
        at = m.end()
    text("r", line[at:], x, y, size)
y += 40
rule(PAD, WIDTH - PAD, y)

# Hack above, Toyon Mono below: the operators with the operator line drawn through both, then
# the letters and figures the picks change.
LABEL = 190
size = 44
scale = size / UPM
for sample, lined in ((OPERATORS, True), (LETTERS, False)):
    y += 34
    for face, name in (("h", "Hack"), ("r", "Toyon Mono")):
        y += 64
        text("r", name, PAD, y, 18, "muted")
        at = len(body)
        end = text(face, sample, PAD + LABEL, y, size)
        if lined:
            # under the glyphs, so it reads as a ruled line and not a strike through them
            rule(PAD + LABEL - 12, end + 12, y - LINE * scale, "accent", 1)
            body.insert(at, body.pop())
    if lined:
        y += 36
        text("r", "the operator line, 700 of 2048", PAD + LABEL, y, 16, "muted")

height = y + PAD

light = "".join(f".{c}{{fill:{l}}}" for c, (l, _) in COLOURS.items())
dark = "".join(f".{c}{{fill:{d}}}" for c, (_, d) in COLOURS.items())
strokes = "".join(f".{c}.stroke{{fill:none;stroke:{l}}}" for c, (l, _) in COLOURS.items())
strokes_dark = "".join(f".{c}.stroke{{fill:none;stroke:{d}}}" for c, (_, d) in COLOURS.items())
style = f"{light}{strokes}@media (prefers-color-scheme:dark){{{dark}{strokes_dark}}}"

defs = "".join(d for f in faces.values() for d in f.defs())
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:.0f}" '
    f'width="{WIDTH}" height="{height:.0f}" role="img" '
    f'aria-label="Toyon Mono specimen: a code sample, and its operators and letters beside Hack\'s">'
    f"<style>{style}</style><defs>{defs}</defs>"
    f'<rect class="bg" width="{WIDTH}" height="{height:.0f}" rx="14"/>'
    f'<rect class="edge stroke" x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1:.0f}" rx="13.5"/>'
    + "".join(body)
    + "</svg>\n"
)
OUT.write_text(svg)
print(f"wrote {OUT.relative_to(ROOT)}, {len(svg) // 1024} kB, {WIDTH} by {height:.0f}")
