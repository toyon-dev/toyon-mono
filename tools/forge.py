#!/usr/bin/env python3
"""Build Toyon Mono from Hack's UFO sources.

Hack is the Bitstream Vera Sans Mono drawing with Source Foundry's redraws, published as UFO
sources with a fontmake build. Toyon Mono is a script over those sources rather than a font kept
in an editor: every choice is a number here, and a build.

    build.sh                 clones Hack, fetches DejaVu, sets up the Python environment, then runs this

What it does, per weight (Hack ships Regular and Bold; the two masters are not point-compatible,
so no weight can be interpolated between them):

  1. rename the font to Toyon Mono and carry Hack's and Bitstream's licence notices along;
  2. apply the picks (picks.json: glyph to face; "dv" copies
     DejaVu's outline in over Hack's redraw, "hk" keeps Hack's, "toyon" applies Toyon's own
     position or drawing, and a glyph absent from the file is Hack's):
       - DejaVu: the glyph copied from DejaVu Sans Mono outline for outline (same units per
         em, same cell, same licence);
       - Toyon: the underscore on the baseline; the chevrons and the multiplication sign
         narrower and taller than the family's; the t with its tail turned up;
     a pick of Menlo's is for the eye only, since Menlo cannot be copied: the glyph stays Hack's
     and the build says so;
  3. apply Toyon's own rules whatever is picked: every operator on one line (OPERATOR_LINE) and
     the enclosures on one span centred on it (ENCLOSURE_SPAN); one width for the dashes and the
     stem's stroke for the bars (OPERATOR_WIDTH, BAR_STROKE); the chevrons at Toyon's size,
     leaned, sharpened and thinned; the cross drawn fresh; the asterisk down on the operator
     line; the slashed zero; round tittles and one size of punctuation dot; the question mark
     drawn as an arc with its terminal turned down, unless picked DejaVu's; the crossbars of
     B E F H and the e lifted to Menlo's height; the quotes at Menlo's weight, the 1 with Menlo's
     flag, the N at Menlo's width;
  4. add the ligatures -> <- <= >= as two-cell glyphs, plus the kern rules that draw || // and
     != closer, and the contextual rule that gives the t its slanted top and tail inside the
     word toyon;
  5. build TTFs with fontmake and write them and their woff2 into fonts/.

Hinting is skipped: Hack's ttfautohint control files are tuned to Hack's outlines, and the
targets here render on macOS and in browsers, which ignore TrueType hints.
"""

import copy
import json
import pathlib
import shutil
import subprocess
import sys

import ufoLib2
from fontTools.misc.transform import Transform
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The lineage: every step the build takes on a glyph, in order, with whose idea it was, written
# to build/lineage.json. Keyed by glyph name here, by character in the file.
#   dv   Vera's drawing, as DejaVu has it      hk   Hack's redraw
#   m    after Menlo                           toyon  Toyon's own
from collections import defaultdict
LINEAGE = defaultdict(list)
HACK_REDREW = set("!$()*,-.013:;?PQZ\\[]_cfgijklr{}~")   # what Hack redrew of Vera's, 5% of the ink and over


def note(name, step, source, kind="move"):
    """kind: "move" for a shift, resize or span of the whole drawing; "draw" for a change inside
    it, a bar lifted, a dot rounded, a tail redrawn; "copy" for an outline taken from another
    face."""
    LINEAGE[name].append({"step": step, "from": source, "kind": kind})
HACK = ROOT / "build" / "hack"
WORK = ROOT / "build" / "hack-work"
OUT = ROOT / "fonts"
REF = ROOT / "build" / "ref"
PICKS = ROOT / "picks.json"

WEIGHTS = {
    "Regular": {"dejavu": "dejavu-sans-mono.ttf", "file": "regular"},
    "Bold": {"dejavu": "dejavu-sans-mono-bold.ttf", "file": "bold"},
}

FAMILY = "Toyon Mono"
VERSION = (0, 1)

LICENSE = (
    "Toyon Mono is a modified version of Hack. Hack is Copyright 2018 Source Foundry Authors and "
    "licensed under the MIT License; the Bitstream Vera Sans Mono drawing it is built on is "
    "Copyright 2003 Bitstream, Inc., under the Bitstream Vera Fonts Copyright, which requires that "
    "modified fonts carry neither the Bitstream nor the Vera name. The glyphs taken from DejaVu "
    "Sans Mono are under the same Bitstream Vera licence with DejaVu's changes in the public "
    "domain. Toyon modifications Copyright 2026 Kyle Shay, MIT License."
)


def rename(font, style):
    info = font.info
    info.familyName = FAMILY
    info.styleName = style
    info.styleMapFamilyName = FAMILY           # name 1, what the menu shows
    info.styleMapStyleName = style.lower()
    info.openTypeNamePreferredFamilyName = FAMILY
    info.openTypeNamePreferredSubfamilyName = style
    info.postscriptFontName = f"ToyonMono-{style}"
    info.postscriptFullName = f"{FAMILY} {style}"
    info.openTypeNameUniqueID = f"Kyle Shay: {FAMILY} {style}: 2026"
    info.openTypeNameManufacturer = "Kyle Shay"
    info.openTypeNameDesigner = "Bitstream, Inc.; Source Foundry Authors (Hack); Toyon modifications by Kyle Shay"
    info.openTypeNameDescription = (
        f"{FAMILY}, a build of Hack with its own glyph picks from the Menlo family, drawn for the "
        "Toyon app and measured against the coding faces its users read."
    )
    info.copyright = (
        "Copyright 2026 Kyle Shay (Toyon modifications). Copyright 2018 Source Foundry Authors "
        "(Hack). Copyright 2003 by Bitstream, Inc. All Rights Reserved. DejaVu changes are in the "
        "public domain."
    )
    info.trademark = ""
    info.openTypeNameLicense = LICENSE
    info.openTypeNameLicenseURL = "https://github.com/kyleshay/toyon-mono"
    info.versionMajor, info.versionMinor = VERSION
    info.openTypeNameVersion = "Version %d.%03d" % VERSION
    info.openTypeOS2VendorID = "TOYO"


def weight_ratio(font, what="letter"):
    """How much heavier this weight is than the Regular, per family of glyph, each read from
    the font's own drawing against the Regular's number. Hack's Bold is not one ratio: its
    letters are 1.53 times the Regular's (the H's bar, 260 against 170), its operators 1.38
    (the equals' bar, 235), its dots 1.09 (the period, 354 against 324), its quotes 1.47 (the
    mark, 256 against 174). One ratio for everything would leave the Bold's operators a fifth
    too light."""
    cap = font.info.capHeight
    if what == "operator":
        ys = sorted({round(p.y) for c in font["equal"].contours for p in c.points})
        bars = [ys[i + 1] - ys[i] for i in range(0, len(ys) - 1, 2)]
        return (sum(bars) / len(bars)) / 171 if bars else 1
    if what == "dot":
        c = font["period"].contours[0]
        return (max(p.x for p in c.points) - min(p.x for p in c.points)) / 324
    if what == "quote":
        c = font["quotesingle"].contours[0]
        return (max(p.x for p in c.points) - min(p.x for p in c.points)) / 174
    ys = sorted({round(p.y) for c in font["H"].contours for p in c.points if cap * 0.3 < p.y < cap * 0.78})
    return (ys[-1] - ys[0]) / 170 if len(ys) >= 2 else 1


def redraw(glyph, draw, transform=None):
    """Replace a glyph's outline with what `draw(pen)` draws, optionally through a transform."""
    glyph.clearContours()
    glyph.clearComponents()
    pen = glyph.getPen()
    draw(TransformPen(pen, transform) if transform else pen)


def transform_in_place(glyph, transform):
    original = copy.deepcopy(glyph)
    redraw(glyph, original.draw, transform)


def bounds(glyph, layer):
    from fontTools.pens.boundsPen import BoundsPen
    pen = BoundsPen(layer)
    glyph.draw(pen)
    return pen.bounds


def by_unicode(font):
    return {u: g.name for g in font for u in g.unicodes}


def copy_from_dejavu(font, dejavu, names):
    """DejaVu's drawing of each named glyph, outline for outline. Both faces have 2048 units per
    em and a 1233 cell, so nothing is scaled. DejaVu is TrueType (quadratic) and Hack's sources
    are cubic, and fontmake's overlap removal only takes cubic, so the contours are converted on
    the way in (Qu2CuPen, exact for quadratics)."""
    cmap = dejavu.getBestCmap()
    glyphset = dejavu.getGlyphSet()
    for name in names:
        glyph = font[name]
        code = glyph.unicodes[0]
        source = glyphset[cmap[code]]
        glyph.clearContours()
        glyph.clearComponents()
        source.draw(Qu2CuPen(glyph.getPen(), max_err=1.0, all_cubic=True))
        glyph.width = dejavu["hmtx"][cmap[code]][0]
        note(name, "DejaVu's outline copied in over Hack's redraw", "dv", "copy")
        round_dots(glyph)


def round_dots(glyph):
    """Round dots are one of Toyon's choices. Any small filled contour in the glyph that is
    boxy (near square, under a fifth of the em, drawn with straight sides or the rounded
    corners Hack gives its i and j tittles) becomes a circle of the box's mean size on the same
    centre, wound the same way. Filled means wound like Hack's outer contours, clockwise, so a
    counter such as the number sign's is never touched; a dot that is already a circle (Hack's
    period) has no straight side and is left alone."""
    from ufoLib2.objects import Point
    for contour in list(glyph.contours):
        pts = contour.points
        if len(pts) > 16 or not any(p.type == "line" for p in pts):
            continue
        xs = [p.x for p in pts]; ys = [p.y for p in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if not (w and h and 0.7 < w / h < 1.3 and w < 410):
            continue
        on = [(p.x, p.y) for p in pts if p.type]
        area = sum(on[i][0] * on[(i + 1) % len(on)][1] - on[(i + 1) % len(on)][0] * on[i][1] for i in range(len(on))) / 2
        if area >= 0:
            continue                               # a hole, not a dot
        cx, cy, r = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (w + h) / 4
        note(glyph.name, "the dot made round", "toyon", "draw")
        K = 0.5523                                 # the cubic circle constant
        # clockwise: right, bottom, left, top
        on = [(cx + r, cy), (cx, cy - r), (cx - r, cy), (cx, cy + r)]
        off = [[(cx + r, cy - r * K), (cx + r * K, cy - r)], [(cx - r * K, cy - r), (cx - r, cy - r * K)],
               [(cx - r, cy + r * K), (cx - r * K, cy + r)], [(cx + r * K, cy + r), (cx + r, cy + r * K)]]
        ring = [Point(*on[0], "curve", smooth=True)]
        for i in range(4):
            ring += [Point(*off[i][0], None), Point(*off[i][1], None)]
            if i < 3:
                ring.append(Point(*on[i + 1], "curve", smooth=True))
        contour.points[:] = ring


DOTTED = ["i", "j"]            # Hack's tittles are rounded squares; Toyon's are round, like its ! and the period


def round_tittles(font):
    for name in DOTTED:
        round_dots(font[name])


def low_asterisk(font):
    """The asterisk on the operator line rather than floating high, where Hack centres it at
    920, and ASTERISK_WIDTH across. Hack's own arms; the position and the size are Toyon's."""
    glyph = font["asterisk"]
    x0, y0, x1, y1 = bounds(glyph, font.layers.defaultLayer)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    scale = ASTERISK_WIDTH / (x1 - x0)             # Hack's is 972 across
    transform_in_place(glyph, Transform().translate(cx, OPERATOR_LINE).scale(scale).translate(-cx, -cy))
    note("asterisk", "moved down onto the operator line, with the other operators", "toyon")


UNDERSCORE_BOTTOM = 0      # the underscore sits on the baseline, not under it
UNDERSCORE_STROKE = 120    # Vera's own; at the stem's 172 it reads as a rule the letters stand on
UNDERSCORE_WIDTH = 1000    # the operator width, in from Vera's 1044, so a_b has air at each side


def underscore_on_baseline(font):
    """The underscore placed with its bottom at UNDERSCORE_BOTTOM. Its thickness and width are
    then set to UNDERSCORE_STROKE and UNDERSCORE_WIDTH by operator_widths(), with the other
    bars."""
    glyph = font["underscore"]
    x0, y0, x1, y1 = bounds(glyph, font.layers.defaultLayer)
    transform_in_place(glyph, Transform().translate(0, UNDERSCORE_BOTTOM - y0))
    note("underscore", "raised to sit on the baseline", "toyon")


# The enclosures. Every bracket, paren, brace, the bar and both slashes run over ENCLOSURE_SPAN,
# a shade under the descender's start to a shade over the ascender, centred on the operator
# line: one span for all nine, so what sits inside a pair reads as held by it, and /> and </
# read as one height. Hack's parens run deeper and shorter (-270 to 1554), its brackets and
# braces deeper and taller (to 1636), and its bar fills the whole line (-483 to 1565) and joins
# into a rule when stacked. Applied after the picks, so a DejaVu paren gets it too.
ENCLOSURE_SPAN = (-230, 1550)
ENCLOSURES = ["parenleft", "parenright", "bracketleft", "bracketright", "braceleft", "braceright", "bar",
              "slash", "backslash"]


# The dashes speak with each other: hyphen, equals, plus and the en dash share one ink width,
# OPERATOR_WIDTH, and the dashes take the hyphen's stroke thickness; the underscore keeps Vera's
# thinner stroke, UNDERSCORE_STROKE, and is brought in from Vera's 1044 to UNDERSCORE_WIDTH, so
# it neither weighs on the line nor runs into its neighbours. Vera's are a mixed set (hyphen
# 821, equals and plus 1057, en dash 615) and the thickness runs from 120 for the underscore to
# 164 for the hyphen. Widths are changed by moving each glyph's ends in or out,
# never by scaling, so stroke thickness and end shapes stay; a point within a stem's reach of
# the centre (the upright of the plus) does not move.
OPERATOR_WIDTH = 1000     # between Vera's hyphen and its equals; Menlo's 1057 reads as the right size in the app
OPERATORS = ["hyphen", "equal", "plus", "endash"]      # the underscore has its own width, below
BARS = ["underscore", "endash", "emdash"]
# And one centre line for all of them. Vera spreads the operators over three: the dashes at
# 563, the hyphen and tilde at 601, the maths signs at 641. Toyon centres every one on a single
# line, OPERATOR_LINE, and that line is the enclosures' centre too (the middle of
# ENCLOSURE_SPAN), so a chevron's tip, a hyphen and a brace's point all meet.
OPERATOR_LINE = 660       # just over Vera's maths line
EQUALS_HEIGHT = 640       # the equals' bars at Menlo's spacing, outside to outside; Vera's is 578
CENTRED = ["hyphen", "equal", "plus", "endash", "emdash", "asciitilde", "multiply", "less", "greater"]


BAR_STROKE = 172          # the dashes at the stem's weight; Vera's hyphen was 164 against its equals at 170


def operator_widths(font):
    layer = font.layers.defaultLayer
    ratio = weight_ratio(font, "operator")
    for name in ["hyphen"] + BARS:
        glyph = font[name]
        x0, y0, x1, y1 = bounds(glyph, layer)
        cy = (y0 + y1) / 2
        if name == "underscore":
            thickness = UNDERSCORE_STROKE * ratio
            t = Transform().translate(0, y0).scale(1, thickness / (y1 - y0)).translate(0, -y0)
            transform_in_place(glyph, t)
            note(name, f"the stroke kept at Vera's {UNDERSCORE_STROKE}, thinner than the dashes", "toyon")
            continue
        thickness = BAR_STROKE * ratio
        t = Transform().translate(0, cy).scale(1, thickness / (y1 - y0)).translate(0, -cy)
        transform_in_place(glyph, t)
        note(name, "the stroke set to the stem's weight", "toyon")
    for name, width in [(n, OPERATOR_WIDTH) for n in OPERATORS] + [("underscore", UNDERSCORE_WIDTH)]:
        glyph = font[name]
        x0, y0, x1, y1 = bounds(glyph, layer)
        cx = (x0 + x1) / 2
        d = (width - (x1 - x0)) / 2
        for contour in glyph.contours:
            for pt in contour.points:
                if pt.x > cx + 150:
                    pt.x += d
                elif pt.x < cx - 150:
                    pt.x -= d
        if abs(d) > 1:
            note(name, f"ends moved to the operator width, {width}", "toyon")
    for name in CENTRED:
        glyph = font[name]
        x0, y0, x1, y1 = bounds(glyph, layer)
        shift = OPERATOR_LINE - (y0 + y1) / 2
        transform_in_place(glyph, Transform().translate(0, shift))
        if abs(shift) > 1:
            note(name, f"centred on the operator line, {OPERATOR_LINE}", "toyon")
    # the equals: its two bars spread to Menlo's spacing, EQUALS_HEIGHT over all, about the
    # operator line (Vera's are 578 outside to outside, Menlo's 640)
    glyph = font["equal"]
    x0, y0, x1, y1 = bounds(glyph, layer)
    cy = (y0 + y1) / 2
    d = (EQUALS_HEIGHT - (y1 - y0)) / 2
    for contour in glyph.contours:
        for pt in contour.points:
            pt.y += d if pt.y > cy else -d
    note("equal", f"the bars spread to Menlo's spacing, {EQUALS_HEIGHT}", "m", "draw")
    # the plus is square: its upright is brought in to the same length as its arms, by the same
    # end-moving, so the cross sits on the operator line as wide as it is tall
    glyph = font["plus"]
    x0, y0, x1, y1 = bounds(glyph, layer)
    cy = (y0 + y1) / 2
    d = (OPERATOR_WIDTH - (y1 - y0)) / 2
    for contour in glyph.contours:
        for pt in contour.points:
            if pt.y > cy + 150:
                pt.y += d
            elif pt.y < cy - 150:
                pt.y -= d
    note("plus", "the upright brought in to make it square", "toyon", "draw")


def span_enclosures(font):
    lo, hi = ENCLOSURE_SPAN
    for name in ENCLOSURES:
        glyph = font[name]
        x0, y0, x1, y1 = bounds(glyph, font.layers.defaultLayer)
        t = Transform().translate(0, lo).scale(1, (hi - lo) / (y1 - y0)).translate(0, -y0)
        transform_in_place(glyph, t)
        note(name, f"set on the enclosure span, {lo} to {hi}", "toyon")


def box(name, w, h, cy):
    """Hack's drawing of `name` resized to a box w by h of 2048 about its own centre, and set on
    the centre line cy. Toyon's < and > are narrower and taller than the family's (911 by 1192
    against 1057 by 1002), which is to say more open."""
    def apply(font):
        glyph = font[name]
        x0, y0, x1, y1 = bounds(glyph, font.layers.defaultLayer)
        cx, cy0 = (x0 + x1) / 2, (y0 + y1) / 2
        t = Transform().translate(cx, cy).scale(w / (x1 - x0), h / (y1 - y0)).translate(-cx, -cy0)
        transform_in_place(glyph, t)
        note(name, f"resized to {w} by {h}", "toyon")
    return apply


ZERO_SLASH_STROKE = 140   # the slash's thickness, measured level: four fifths of the Regular stem, and thickened for
                          # the Bold by the operator ratio, as the other bars are
ZERO_SLASH_LEAN = 7.5     # the slant, in degrees shallower than the counter's own diagonal, so each weight's slash
                          # suits its counter: 58 from horizontal in the Regular (diagonal 65.5), about Menlo's angle,
                          # and 62 in the Bold's narrower counter (69.5). At 0, on the diagonal, the slash runs so
                          # close to the ring's sides at 11 to 14 px that the counter barely splits; at 15 it reads
                          # crossed out


def slashed_zero(font):
    """A slashed zero where the family's is dotted, built as Menlo's is. Hack's zero minus its
    dot, plus a diagonal through the counter, ZERO_SLASH_STROKE thick, on the slant of the
    counter's diagonal less ZERO_SLASH_LEAN, each end in the middle of the ring, measured along
    the slant on the outline itself, so overlap removal buries it and nothing shows outside.
    Tried and dropped: ends past the ring, which read as the letter O with a stroke and muddy
    small sizes; and a bar floating in the counter, which suits the Regular but in the Bold's
    narrow counter has to shrink to a speck."""
    import math
    from fontTools.pens.basePen import BasePen
    glyph = font["zero"]
    def area(c):
        xs = [p.x for p in c.points]; ys = [p.y for p in c.points]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))
    contours = sorted(glyph.contours, key=area)
    dot, counter, ring = contours
    glyph.contours.remove(dot)
    xs = [p.x for p in counter.points]; ys = [p.y for p in counter.points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    slant = math.atan2(y1 - y0, x1 - x0) - math.radians(ZERO_SLASH_LEAN)
    dx, dy = math.cos(slant), math.sin(slant)

    class Flatten(BasePen):                        # the outline as a polyline, to cut it with the slant
        def __init__(self):
            super().__init__(None); self.pts = []; self.cur = None
        def _moveTo(self, p): self.cur = p; self.pts.append(p)
        def _lineTo(self, p): self.cur = p; self.pts.append(p)
        def _curveToOne(self, p1, p2, p3):
            (ax, ay), (bx, by), (qx, qy), (rx, ry) = self.cur, p1, p2, p3
            for i in range(1, 17):
                t = i / 16; u = 1 - t
                self.pts.append((u*u*u*ax + 3*u*u*t*bx + 3*u*t*t*qx + t*t*t*rx, u*u*u*ay + 3*u*u*t*by + 3*u*t*t*qy + t*t*t*ry))
            self.cur = p3
        def _closePath(self): self.pts.append(self.pts[0])

    def reach(contour, sign):
        """Distance from the centre to the contour along the slant, in the direction sign."""
        pen = Flatten(); contour.draw(pen); pts = pen.pts
        ddx, ddy = sign * dx, sign * dy
        hits = []
        for (px, py), (qx, qy) in zip(pts, pts[1:]):
            ex, ey = qx - px, qy - py
            det = ddx * ey - ddy * ex            # the ray (cx,cy)+t(ddx,ddy) against the segment p+s(e)
            if abs(det) < 1e-9:
                continue
            wx, wy = px - cx, py - cy
            t = (wx * ey - wy * ex) / det
            s = (ddy * wx - ddx * wy) / det
            if t > 0 and 0 <= s <= 1:
                hits.append(t)
        return min(hits)

    ends = []
    for sign in (-1, 1):
        end = (reach(counter, sign) + reach(ring, sign)) / 2
        ends.append((cx + sign * dx * end, cy + sign * dy * end))
    (ax, ay), (bx, by) = ends
    h = ZERO_SLASH_STROKE * weight_ratio(font, "operator") / 2 * dy     # half the stroke across the slant
    nx, ny = -dy * h, dx * h
    # wound the same way as the outer ring (clockwise in Hack's sources), so overlap removal
    # unions it with the ring instead of cutting a slash-shaped hole through it
    pen = glyph.getPen()
    pen.moveTo((ax + nx, ay + ny)); pen.lineTo((bx + nx, by + ny)); pen.lineTo((bx - nx, by - ny)); pen.lineTo((ax - nx, ay - ny)); pen.closePath()
    note("zero", "the dot removed and a slash drawn through, as Menlo's", "m", "draw")


# The t's tail: Toyon's signature, a diagonal rising out of the stem's foot, which t.toyon
# carries inside the word toyon (SIGNATURE_WORD below). The other constructions are options on
# T_HOOK, each with its own knobs.
T_HOOK = "diagonal"  # "diagonal": a full-thickness diagonal rising straight out of the stem's curve;
                     # "square": the foot cut flat and the tail a straight stroke off its corner, like the 1's flag;
                     # "flick": Hack's tail with a rising slanted cut at its end; "rise": a thin hook;
                     # "swoop": a serif t's tail, one continuous curve from mid-stem through the foot and up;
                     # "vera": the tail as DejaVu draws it
T_TAIL_ANGLE, T_TAIL_THICK, T_TAIL_REACH = 39.4, 148, 401   # the diagonal: its angle, its thickness across, and how far past the stem's inner edge its tip reaches
T_FLICK_LIFT = 230       # how far the flick's top corner rises
# The swoop: where the tail's centreline ends (from the stem's inner edge, and above the
# baseline), the angle it leaves at, and how thick it is there.
T_SWOOP_REACH, T_SWOOP_HEIGHT, T_SWOOP_ANGLE, T_SWOOP_THICK = 380, 180, 38, 70
# The swoop's taper: the outer edge is one smooth curve and the inside thins; the stroke keeps
# the stem's width to the first fraction of the centreline, eases to T_SWOOP_THICK by the second,
# and holds it to the end.
T_SWOOP_TAPER = (0.15, 1.0)
# The swoop's foot: the outer edge swells by this much at the bottom of the bend, as a serif t's
# bowl is heaviest at its lower left, fading out either side; centred at this fraction of the
# centreline.
T_SWOOP_BULGE, T_SWOOP_BULGE_AT = 0, 0.4


def hooked_t(font, name="t"):
    """Toyon's t: the tail does not end level, it turns up. Hack's t is kept whole apart from
    the end of its tail, and T_HOOK picks the construction. Two of them keep Hack's tail and
    change only its end:
      flick: the tail's top edge lifts over its last third and the end is cut on a slant, high
             on the outside, so the stroke reads as flicking up and keeps its full thickness;
      rise:  the tail continues as a thin diagonal stroke with a square cut, which at text size
             reads as a blob."""
    import math
    from ufoLib2.objects import Point
    if T_HOOK == "vera":                           # the tail as DejaVu draws it, for the trial page
        return
    glyph = font[name]
    contour = max(glyph.contours, key=lambda c: len(c.points))
    pts = contour.points
    xh = font.info.xHeight
    right = max(p.x for p in pts if p.y < xh / 2)
    idx = [i for i, p in enumerate(pts) if p.x == right and p.y < xh / 2]
    if len(idx) != 2 or idx[1] != idx[0] + 1:
        return
    note("t", "the tail redrawn to rise, Toyon's signature", "toyon", "draw")
    inner_start = pts[idx[0] - 1]                 # where the tail's top edge begins its level run
    top_y, bottom_y = pts[idx[0]].y, pts[idx[1]].y
    k = weight_ratio(font)                         # Regular's stem; Bold scales with its own
    ix, iy = inner_start.x, inner_start.y

    def stem_foot(pts):
        """Rotate the contour so it starts at the foot of the stem's inner edge, the point where
        the straight edge ends and the tail begins (614,369 in Regular), and return that point
        and the index of its twin on the outer edge (430,369); everything between the two is the
        tail. Found by geometry, not by counting points back from the tail's corner: DejaVu's t,
        copied in with its curves converted, has more points there than Hack's, and counting put
        the joins on the curve instead of at its start, which notched the foot."""
        stem = [p for p in pts if xh * 0.3 < p.y < xh * 0.7]   # below the crossbar (the Bold's bottom is at 0.8 of the x-height), above the tail
        in_x, out_x = max(p.x for p in stem), min(p.x for p in stem)
        inner = min((p for p in pts if p.type and p.x == in_x), key=lambda p: p.y)   # on-curve only: the
        outer = min((p for p in pts if p.type and p.x == out_x), key=lambda p: p.y)  # first handle shares its x
        start = pts.index(inner)
        pts[:] = pts[start:] + pts[:start]
        return pts[0], pts.index(outer)
    if T_HOOK == "square":
        # the foot square, like the figure one's: the stem runs straight down to the bottom, the
        # bottom is flat, and the tail is a straight stroke at the flag's slope (25.5 degrees)
        # and thickness leaving the stem's inner edge, cut vertically at the tip. No curve.
        inner, j = stem_foot(pts)                      # (614, 369) and the index of (430, 369)
        outer = pts[j]
        a = math.radians(25.5)
        d = (math.cos(a), math.sin(a)); n = (math.sin(a), -math.cos(a))
        thick = 171 * k
        slope = d[1] / d[0]
        bottom = -16
        end_x = inner.x + 346
        y_leave = 150 * k                              # where the tail's inner edge leaves the stem
        ei = (end_x, y_leave + slope * (end_x - inner.x))
        eo = (end_x, ei[1] + n[1] * thick - slope * n[0] * thick)
        po = (end_x - (eo[1] - bottom) / slope, bottom)   # the outer line meets the flat bottom
        new = [
            Point(inner.x, y_leave, "line"),
            Point(*ei, "line"),
            Point(*eo, "line"),
            Point(*po, "line"),
            Point(outer.x, bottom, "line"),
            Point(outer.x, 158, "line"),
        ]
        pts[1:j + 1] = new
        top = [pt for pt in pts if pt.y > xh + 200 and outer.x - 1 <= pt.x <= inner.x + 1]
        if len(top) == 2:
            y = max(pt.y for pt in top)
            for pt in top:
                pt.y = y
        note("t", "the foot cut square and the tail a straight stroke, like the 1's flag", "toyon", "draw")
        return
    if T_HOOK == "diagonal":
        # the diagonal, in units of 2048: the stem's edges run straight down to 158, the outer
        # turns through a quarter curve to the bottom at -16 and runs on to where the diagonal
        # begins; the inner turns at once into the diagonal. The diagonal rises at T_TAIL_ANGLE,
        # thinner than the stem (148 across against 184), to a cut square to the stroke. Hack's
        # stem is the same width at the same place, so the tail sits on it unchanged; the Bold
        # scales the diagonal's thickness with its stem.
        inner, j = stem_foot(pts)                      # (614, 369) and the index of (430, 369)
        outer = pts[j]
        # under 30 degrees the diagonal takes the figure one's flag as its model instead: the
        # flag's slope and a vertical cut at the tip, mirrored
        a = math.radians(T_TAIL_ANGLE)
        d = (math.cos(a), math.sin(a))
        n = (math.sin(a), -math.cos(a))                # the normal, outwards and down
        thick = T_TAIL_THICK * k
        end_x = inner.x + T_TAIL_REACH                 # the tip, 960 in Regular at 346
        ei = (end_x, 124 + d[1] / d[0] * (end_x - (inner.x + 26)))
        if T_TAIL_ANGLE > 30:                          # the cut square to the stroke
            eo = (ei[0] + n[0] * thick, ei[1] + n[1] * thick)
        else:                                          # the flag's: a vertical cut
            eo_y = ei[1] + n[1] * thick - d[1] / d[0] * (n[0] * thick)
            eo = (end_x, eo_y)
        # the two joins: the inner edge of the tail leaves the stem's inner edge directly, a
        # clean inside corner like a k's, with no level run between; the outer diagonal begins
        # above the bottom at 18, and the foot's curve rises into it along the diagonal's own
        # direction
        slope = d[1] / d[0]
        y_join = ei[1] - slope * (ei[0] - inner.x)   # where the inner line meets the stem
        po = (eo[0] - (eo[1] - 18) / slope, 18)
        new = [
            Point(inner.x, y_join, "line"),
            Point(*ei, "line"),
            Point(*eo, "line"),
            Point(*po, "line", smooth=True),             # a line point: the diagonal arrives straight, the curve leaves along it
            Point(po[0] - d[0] * 60, po[1] - d[1] * 60, None), Point(outer.x + 217, -16, None), Point(outer.x + 186, -16, "curve", smooth=True),
            Point(outer.x + 90, -16, None), Point(outer.x, 60, None), Point(outer.x, 158, "curve", smooth=True),
        ]
        pts[1:j + 1] = new
        return
    if T_HOOK == "swoop":
        # a serif t's tail: the stem does not stop and turn, it bends. One cubic centreline from the stem's middle at
        # mid-x-height, leaving straight down, through the foot and up to the terminal; the
        # stroke thins from the stem's width to T_SWOOP_THICK along it, and the end is cut
        # square to the stroke. Each edge is then one cubic fitted to the offset curve, with the
        # tangents fixed (vertical at the stem, the terminal's angle at the end) and the two
        # handle lengths found by search, so the outline stays four curve points.
        inner, j = stem_foot(pts)                      # (614, 369) and the index of (430, 369)
        outer = pts[j]
        inner.smooth = True
        y0 = inner.y
        cx = (inner.x + outer.x) / 2
        w0 = inner.x - outer.x
        w1 = T_SWOOP_THICK * k
        a = math.radians(T_SWOOP_ANGLE)
        d = (math.cos(a), math.sin(a))
        n = (math.sin(a), -math.cos(a))                # outwards and down
        p3 = (inner.x + T_SWOOP_REACH, T_SWOOP_HEIGHT)
        def centre(h0, h1):
            p0, p1, p2 = (cx, y0), (cx, y0 - h0), (p3[0] - d[0] * h1, p3[1] - d[1] * h1)
            def at(t):
                u = 1 - t
                x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
                y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
                dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
                dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
                L = math.hypot(dx, dy) or 1
                return (x, y), (dx / L, dy / L)
            return at
        def edge_samples(at, side, N=60):
            out = []
            for i in range(N + 1):
                t = i / N
                (x, y), (tx, ty) = at(t)
                u = min(1, max(0, (t - T_SWOOP_TAPER[0]) / (T_SWOOP_TAPER[1] - T_SWOOP_TAPER[0])))
                w = w0 + (w1 - w0) * (u * u * (3 - 2 * u))   # eased, so the taper starts without a corner
                nx, ny = ty, -tx                        # right-hand normal: towards the outer edge
                # the outer edge is the centreline offset by the stem's half width throughout; the
                # inner edge carries the whole taper, so the outside stays one smooth curve
                bulge = T_SWOOP_BULGE * k * math.exp(-((t - T_SWOOP_BULGE_AT) / 0.22) ** 2)
                off = w0 / 2 + bulge if side > 0 else w0 / 2 - w
                out.append((x + nx * off, y + ny * off))
            return out
        # the foot: the outer edge's lowest point lands on the baseline's overshoot, -16, by
        # searching the first handle's length; the second handle is a fixed fraction of the reach
        h1 = T_SWOOP_REACH * 0.9
        lo, hi = 50, 900
        for _ in range(40):
            h0 = (lo + hi) / 2
            bottom = min(y for _, y in edge_samples(centre(h0, h1), +1))
            if bottom > -16:
                lo = h0
            else:
                hi = h0
        at = centre(h0, h1)
        def fit(samples, p0, t0, p1, t1):
            best = None
            for ha in range(20, 800, 10):
                for hb in range(20, 800, 10):
                    c1 = (p0[0] + t0[0] * ha, p0[1] + t0[1] * ha)
                    c2 = (p1[0] - t1[0] * hb, p1[1] - t1[1] * hb)
                    err = 0
                    for i in range(0, 61, 4):
                        t = i / 60; u = 1 - t
                        x = u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0]
                        y = u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1]
                        err += min((x - sx) ** 2 + (y - sy) ** 2 for sx, sy in samples)
                    if best is None or err < best[0]:
                        best = (err, c1, c2)
            return best[1], best[2]
        outer_s = edge_samples(at, +1)
        inner_s = edge_samples(at, -1)
        (p_end, d_end) = at(1)
        ei, eo = inner_s[-1], outer_s[-1]
        # each edge as two cubics meeting halfway along, where the taper is steepest; one cubic
        # cannot follow an edge that thins on one side only
        def two(samples, p0, t0, p1, t1):
            m = len(samples) // 2
            mid = samples[m]
            tm = (samples[m + 1][0] - samples[m - 1][0], samples[m + 1][1] - samples[m - 1][1])
            L = math.hypot(*tm); tm = (tm[0] / L, tm[1] / L)
            a1, a2 = fit(samples[:m + 1], p0, t0, mid, tm)
            b1, b2 = fit(samples[m:], mid, tm, p1, t1)
            return [Point(*a1, None), Point(*a2, None), Point(*mid, "curve", smooth=True), Point(*b1, None), Point(*b2, None)]
        new = [
            *two(inner_s, (inner.x, y0), (0, -1), ei, d_end), Point(*ei, "curve"),
            Point(*eo, "line"),
            *two(list(reversed(outer_s)), eo, (-d_end[0], -d_end[1]), (outer.x, y0), (0, 1)), Point(outer.x, y0, "curve", smooth=True),
        ]
        pts[1:j + 1] = new
        note("t", "the tail one continuous curve from the stem through the foot, a serif t's", "toyon", "draw")
        return
    if T_HOOK == "flick":
        # top edge: level to a third of the way, then a curve lifting to the end; the end cut
        # runs from the lifted top corner down and back to the bottom corner; bottom edge level
        lift = T_FLICK_LIFT * k
        end_x = right + 30 * k
        knee_x = ix + (end_x - ix) * 0.35
        new = [
            Point(knee_x, iy, "line"),
            Point(knee_x + (end_x - knee_x) * 0.55, iy, None), Point(end_x - 40 * k, iy + lift * 0.55, None), Point(end_x, iy + lift, "curve"),
            Point(right - 60 * k, bottom_y, "line"),
        ]
        pts[idx[0]:idx[1] + 1] = new
        return
    inner_start.smooth = True
    ux, uy = 0.5, math.sqrt(3) / 2                # the rise, 60 degrees
    nx, ny = uy, -ux                              # its normal, towards the outer edge
    ox, oy = right - 150 * k, bottom_y            # where the outer edge leaves the flat bottom
    w = (ox - ix) * nx + (oy - iy) * ny           # distance between the two parallel edges
    L = 250 * k
    inner_end = (ix + ux * L, iy + uy * L)
    outer_end = (inner_end[0] + nx * w, inner_end[1] + ny * w)
    s = 96 * k                                    # the fillet into the flat bottom
    fillet = (ox + ux * s, oy + uy * s)
    knee = 120 * k                                # the inner edge curves into the rise over this length
    knee_end = (ix + ux * knee, iy + uy * knee)
    new = [
        Point(ix + 40 * k, iy, None), Point(knee_end[0] - ux * 30 * k, knee_end[1] - uy * 30 * k, None), Point(*knee_end, "curve"),
        Point(*inner_end, "line"),
        Point(*outer_end, "line"),
        Point(*fillet, "line"),
        Point(ox + ux * s * 0.5, oy + uy * s * 0.5 - 8 * k, None), Point(ox - 8 * k, oy, None), Point(ox - 42 * k, oy, "curve"),
    ]
    pts[idx[0]:idx[1] + 1] = new


def slanted_compare(font, name, chevron):
    """Toyon's <= and >=: the chevron, with a second stroke under it parallel to the lower arm,
    rather than the family's sign with a level bar. Two cells wide, the chevron lifted a little and the bar below it, centred in the pair. Built
    from the chevron as the picks left it."""
    src = font[chevron]
    x0, y0, x1, y1 = bounds(src, font.layers.defaultLayer)
    cell = src.width
    cy = (y0 + y1) / 2
    drop = 180                                    # the gap between the arm and the bar, one stroke
    glyph = font.newGlyph(name)
    glyph.width = 2 * cell
    # the whole sign, chevron and bar, is centred on the operator line: the chevron rises by
    # half of what the bar adds below it, the gap plus the bar's vertical thickness
    import math
    bx0, _, bx1, _ = bounds(font["bar"], font.layers.defaultLayer)
    across0 = CHEVRON_STROKE * weight_ratio(font, "operator")
    arm_angle = math.atan(((y1 - y0) / 2) / (x1 - x0))
    lift = (drop + across0 / math.cos(arm_angle)) / 2
    shift = Transform().translate(cell - (x0 + x1) / 2, lift)
    src.draw(TransformPen(glyph.getPen(), shift))
    # the lower arm's outer edge, read off the chevron's own points: from the far end's bottom
    # corner to the apex's lower corner (the apex is a short vertical cut, so the bbox centre is
    # not on the edge). The bar is that edge's run from 14% in to the far end, as thick as the
    # arm is tall at the far end, shifted down.
    pts0 = [(p.x, p.y) for c in src.contours for p in c.points]
    apex_x = x0 if chevron == "less" else x1
    # the bar is the lower arm itself: its two end corners (the two lower points farthest from
    # the apex, cut square to the stroke) and, toward the apex, the two edges' points at 14% of
    # the run, the whole shifted down by `drop`. So the bar's end matches the arm's end, cut for
    # cut, and the two read as one stroke repeated.
    import math
    pts0 = [(p.x, p.y) for c in src.contours for p in c.points]
    apex_x = x0 if chevron == "less" else x1
    lower = sorted((p for p in pts0 if p[1] < cy), key=lambda p: -abs(p[0] - apex_x))[:2]
    outer_end, inner_end = sorted(lower, key=lambda p: p[1])
    y_apex = min(y for x, y in pts0 if abs(x - apex_x) < 1)
    bx0, _, bx1, _ = bounds(font["bar"], font.layers.defaultLayer)
    across = CHEVRON_STROKE * weight_ratio(font, "operator")
    angle = math.atan(abs(outer_end[1] - y_apex) / abs(outer_end[0] - apex_x))
    tv = across / math.cos(angle)
    far_x = outer_end[0]
    start_x = apex_x + (far_x - apex_x) * 0.02   # from right under the apex to the arm's end
    start_y = y_apex + (outer_end[1] - y_apex) * 0.02
    pts = [(start_x, start_y), outer_end, inner_end, (start_x, start_y + tv)]
    pts = [(x, y - tv) for x, y in pts]            # the arm's outer edge is its lower edge; the bar hangs below it by its own thickness
    if chevron == "less":
        pts = [pts[0], pts[3], pts[2], pts[1]]     # clockwise, like the chevron
    pen = TransformPen(glyph.getPen(), Transform().translate(cell - (x0 + x1) / 2, lift - drop))
    pen.moveTo(pts[0])
    for pt in pts[1:]:
        pen.lineTo(pt)
    pen.closePath()
    return glyph


def two_cell(font, name, source, stretch=True):
    """A ligature glyph two cells wide from a sign Hack already draws (its arrow or comparison
    sign). Stretched, the sign is widened across both cells, so -> spans the pair the way the
    two characters did. Centred, the sign keeps its proportions, grows a fifth, and sits in the
    middle of the two cells with air either side."""
    src = font[source]
    x0, y0, x1, y1 = bounds(src, font.layers.defaultLayer)
    cell = src.width
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if stretch:
        target_w = 2 * cell - 2 * (cell - (x1 - x0)) / 2 * 0.6     # keep some air at each side
        t = Transform().translate(cell, 0).scale(target_w / (x1 - x0), 1).translate(-cx, 0)
    else:
        t = Transform().translate(cell, cy).scale(1.2).translate(-cx, -cy)
    glyph = font.newGlyph(name)
    glyph.width = 2 * cell
    src.draw(TransformPen(glyph.getPen(), t))
    return glyph


# The ligatures, each a two-cell glyph built from a sign Hack already draws and substituted in
# calt; and the kern rules, which draw || // and != closer without changing any advance (the
# first glyph moves right inside its cell and the second moves left). Each sequence
# is a row of picks.json: picked "dv" it is left plain, picked "hk" the sign is stretched across the
# pair, picked "toyon" the comparison is drawn Toyon's way (the chevron with a bar parallel to
# its lower arm) and an arrow is centred in the pair at its own proportions.
LIGS = {
    "<=": ("less_equal.liga", "lessequal", "sub less equal by less_equal.liga;", "less"),
    ">=": ("greater_equal.liga", "greaterequal", "sub greater equal by greater_equal.liga;", "greater"),
    "->": ("hyphen_greater.liga", "arrowright", "sub hyphen greater by hyphen_greater.liga;", None),
    "<-": ("less_hyphen.liga", "arrowleft", "sub less hyphen by less_hyphen.liga;", None),
}
# The pairs drawn closer: each glyph moves inside its own cell, the first right and the second
# left by the amount given (of 2048), so the advance and the grid are untouched.
KERNS = {
    "||": ("bar", "bar", 40),         # a little closer; twice this reads as a wall
    "//": ("slash", "slash", 60),
    "!=": ("exclam", "equal", 140),   # closer, not touching
}


def kern_rule(first, second, by):
    rule = f"pos {first}' <{by} 0 0 0> {second};\n    pos {first} {second}' <-{by} 0 0 0>;"
    if (first, second) == ("exclam", "equal"):
        # !== as well: the second equals follows the first by the same amount, so the pair of
        # equals keeps its own spacing and only the gap after the exclamation mark closes
        rule += f"\n    pos {first} {second} {second}' <-{by} 0 0 0>;"
    return rule


# The signature: the rising tail on the t, but only inside the word "toyon". The t itself stays
# Vera's apart from its top; t.toyon carries the tail, and a contextual rule swaps it in when
# the t is followed by o y o n (so toyon, toyon.dev, ~/.toyon, but not Toyon with its capital).
# On every t it is too much of a good thing.
SIGNATURE_WORD = "toyon"


# The top of the signature t's stem: not Vera's flat cut but a slant, the left corner lower,
# rising to the right corner at the full height. The angle is the knob, so the Bold's wider stem
# drops its left corner further and the slant stays the same. The plain t keeps Vera's flat top.
T_TOP_ANGLE = 28


def cut_t_top(font, name="t"):
    import math
    glyph = font[name]
    contour = max(glyph.contours, key=lambda c: len(c.points))
    top = max(p.y for p in contour.points)
    corners = sorted((p for p in contour.points if p.y == top), key=lambda p: p.x)
    if len(corners) != 2:
        return
    corners[0].y = round(top - (corners[1].x - corners[0].x) * math.tan(math.radians(T_TOP_ANGLE)))
    note(name, "the top of the stem cut on a slant, the left corner lower", "toyon", "draw")


def signature_t(font):
    import copy
    glyph = font.newGlyph("t.toyon")
    glyph.width = font["t"].width
    for c in font["t"].contours:
        glyph.contours.append(copy.deepcopy(c))
    cut_t_top(font, "t.toyon")
    hooked_t(font, "t.toyon")
    order = list(font.lib.get("public.glyphOrder", []))
    if "t.toyon" not in order:
        order.append("t.toyon")
    font.lib["public.glyphOrder"] = order
    note("t", f"Vera's; the slanted top and rising tail only in the word {SIGNATURE_WORD}, by a contextual rule", "toyon", "draw")
    rest = " ".join(SIGNATURE_WORD[1:])
    return f"sub t' {rest} by t.toyon;"


def ligatures(font, chosen):
    subs, order = [signature_t(font)], list(font.lib.get("public.glyphOrder", []))
    for seq, (name, source, rule, chevron) in LIGS.items():
        if chosen.get(seq) == "dv":
            continue
        if chosen.get(seq) == "toyon" and chevron:
            slanted_compare(font, name, chevron)
        else:
            two_cell(font, name, source, stretch=chosen.get(seq) != "toyon")
        subs.append(rule)
        if name not in order:
            order.append(name)
    font.lib["public.glyphOrder"] = order
    kerns = [kern_rule(*spec) for seq, spec in KERNS.items() if chosen.get(seq) != "dv"]
    fea = "\n# Toyon: the ligatures, as two-cell glyphs. Added by tools/hack-forge.py.\n"
    if subs:
        fea += "feature calt {\n    " + "\n    ".join(subs) + "\n} calt;\n"
    if kerns:
        fea += "\n# Toyon: kern-bars, the pair drawn closer inside their own cells.\nfeature kern {\n    " + "\n    ".join(kerns) + "\n} kern;\n"
    font.features.text = font.features.text + fea


# The scripted picks per face, keyed by the character. A pick of Menlo's is a hand item, since
# Menlo cannot be copied: the glyph stays Hack's.
# The crossbars of H E F set with their underside at CAP_BAR_BOTTOM, Menlo's height: Vera puts
# them at 711 (53% of the cap height), Menlo at 751 (56%), which is what makes Menlo's capitals
# read more open; Hack's F sits lower still at 693. The bar is the only run of points in the
# middle of those three glyphs, so moving every point between a third and two thirds of the cap
# height moves the bar and nothing else. The B's middle is two bowls meeting and is moved as a
# band, see below.
CAP_BAR_BOTTOM = 751
CAP_BAR_GLYPHS = ["H", "E", "F"]


def lift_cap_bars(font):
    cap = font.info.capHeight
    for name in CAP_BAR_GLYPHS:
        mid = [pt for contour in font[name].contours for pt in contour.points if cap / 3 < pt.y < cap * 2 / 3]
        lift = CAP_BAR_BOTTOM * cap / 1493 - min(pt.y for pt in mid)
        for pt in mid:
            pt.y += lift
        note(name, f"crossbar lifted {round(lift)} to Menlo's height", "m", "draw")
    # the B's middle, where its two bowls meet: rather than moving a band of points, which kinks
    # the curves either side, the whole region between the bottom and top strokes is remapped
    # smoothly, the lower bowl stretched and the upper compressed so the junction lands 40
    # higher (Menlo's 917 against Vera's 877). The two horizontal strokes keep their thickness.
    b = font["B"]
    outer = max(b.contours, key=lambda c: len(c.points))
    counters = sorted((c for c in b.contours if c is not outer), key=lambda c: min(p.y for p in c.points))
    stroke = min(p.y for p in counters[0].points)            # the bottom stroke's thickness: the lower counter's floor, 166
    top = cap - (cap - max(p.y for p in counters[1].points))  # the upper counter's ceiling
    lo, hi = stroke, max(p.y for p in counters[1].points)
    junction = (max(p.y for p in counters[0].points) + min(p.y for p in counters[1].points)) / 2   # the middle stroke's centre, 795
    lift = 40 * cap / 1493
    target = junction + lift
    for contour in b.contours:
        for pt in contour.points:
            if lo < pt.y < hi:
                pt.y = lo + (pt.y - lo) * (target - lo) / (junction - lo) if pt.y < junction else target + (pt.y - junction) * (hi - target) / (hi - junction)
    note("B", f"the middle lifted {round(lift)} to Menlo's height", "m", "draw")


# The quote marks at Menlo's weight: Vera's are 174 wide and 555 tall, Menlo's 224 wide and 612
# tall, reaching above the cap, and the two marks of the double quote sit 309 apart against
# Vera's 209. Each mark is scaled about its own base and centre, and the pair is spread
# symmetrically about the cell's middle.
QUOTE_WIDTH, QUOTE_HEIGHT, QUOTE_GAP = 224, 612, 309


CURLY = ["quoteleft", "quoteright", "quotedblleft", "quotedblright", "quotesinglbase", "quotedblbase"]


def menlo_quotes(font):
    layer = font.layers.defaultLayer
    # the curly quotes grow by the same factors Menlo applied to the straight marks, 29% wider
    # and 10% taller, each about its own base and centre, the doubles spread to the same gap;
    # they are comma shapes, so they are not forced to the bars' exact size
    k = weight_ratio(font, "quote")                # read from the mark before it is resized
    fx, fy = QUOTE_WIDTH / 174, QUOTE_HEIGHT / 555   # growth factors, the same in every weight
    for name in CURLY:
        if name not in font:
            continue
        glyph = font[name]
        marks = list(glyph.contours)
        boxes = []
        for c in marks:
            xs = [p.x for p in c.points]; ys = [p.y for p in c.points]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        cell = glyph.width
        n = len(marks)
        for i, (c, (x0, y0, x1, y1)) in enumerate(zip(marks, boxes)):
            cx = (x0 + x1) / 2
            order = sorted(range(n), key=lambda j: boxes[j][0]).index(i)
            w = (x1 - x0) * fx
            target = cell / 2 if n == 1 else cell / 2 + (order - 0.5) * (QUOTE_GAP + w)
            t = Transform().translate(target, y0).scale(fx, fy).translate(-cx, -y0)
            for pt in c.points:
                pt.x, pt.y = t.transformPoint((pt.x, pt.y))
        note(name, "grown as Menlo grew the straight quotes, 29% wider and 10% taller", "m")
    for name in ["quotedbl", "quotesingle"]:
        glyph = font[name]
        marks = list(glyph.contours)
        boxes = []
        for c in marks:
            xs = [p.x for p in c.points]; ys = [p.y for p in c.points]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        cell = glyph.width
        n = len(marks)
        for i, (c, (x0, y0, x1, y1)) in enumerate(zip(marks, boxes)):
            cx = (x0 + x1) / 2
            # where the mark's centre goes: the cell's middle for a single, either side of it for a pair
            order = sorted(range(n), key=lambda k: boxes[k][0]).index(i)
            qw, qh = QUOTE_WIDTH * k, QUOTE_HEIGHT * k
            target = cell / 2 if n == 1 else cell / 2 + (order - 0.5) * (QUOTE_GAP + qw)
            t = Transform().translate(target, y0).scale(qw / (x1 - x0), qh / (y1 - y0)).translate(-cx, -y0)
            for pt in c.points:
                pt.x, pt.y = t.transformPoint((pt.x, pt.y))
        note(name, "at Menlo's weight, height and spacing", "m")


# The question mark's left terminal turned down: Hack's arc ends at the left in a vertical cut
# (the stroke pointing left), Toyon's continues down and ends level at the x-height (the stroke
# pointing down). Two constructions: "arc" draws the whole mark fresh (question_terminal);
# "vera" keeps Hack's arc to its leftmost point and runs the outer edge straight down from there
# to QUESTION_TERMINAL, which reads like the tilde's flat terminal.
QUESTION_TERMINAL = 1130
QUESTION_TURN = 1290      # where the arc's outer edge becomes the vertical drop to the terminal


QUESTION_STYLE = "arc"


def vera_question(font):
    """Hack's question mark, which is Vera's drawing, with only the left terminal changed: where
    Vera cuts the hook vertically, the arc's two edges continue with their own curvature, the
    outer sweeping down and round into a vertical drop, the inner likewise, to a level cut at
    the x-height. Each new curve leaves the arc along the arc's final tangent and arrives
    upright, so there is no splice to see. The dot is the exclamation mark's."""
    import copy
    from ufoLib2.objects import Point
    glyph = font["question"]
    k = weight_ratio(font)
    body = max(glyph.contours, key=lambda c: len(c.points))
    pts = body.points
    left = min(p.x for p in pts)
    cut = sorted((i for i, p in enumerate(pts) if abs(p.x - left) < 1), key=lambda i: pts[i].y)
    if len(cut) != 2:
        return
    i_in, i_out = cut                              # the cut's inner (lower) and outer (upper) corners
    near = 40 * k                                  # an on-curve point this close to a corner is part of the corner (the Bold has two)
    def close(a, b):
        return abs(a.x - b.x) < near and abs(a.y - b.y) < near
    # the arc's last on-curve points before each corner, and their incoming tangents
    def back(i):
        j = i - 1
        while pts[j].type is None or close(pts[j], pts[i]):
            j -= 1
        return j
    j_in = back(i_in)                              # the inner edge arrives at the cut from here
    k_out = i_out + 1                              # the outer edge leaves the cut toward here
    while pts[k_out % len(pts)].type is None or close(pts[k_out % len(pts)], pts[i_out]):
        k_out += 1
    k_out %= len(pts)
    arc_in = pts[j_in]; h_in = pts[j_in + 1] if pts[j_in + 1].type is None else arc_in
    arc_out = pts[k_out]; h_out = pts[k_out - 1] if pts[k_out - 1].type is None else arc_out
    bottom = font.info.xHeight                     # the level cut, at the x-height
    stem = 172 * k
    inner_x = left + stem * 0.95
    # the inner edge: from arc_in, along its tangent (toward its handle), curving to vertical at
    # inner_x; handle lengths are fractions of the curve's own span, so both weights behave
    tx, ty = h_in.x - arc_in.x, h_in.y - arc_in.y
    tl = (tx * tx + ty * ty) ** 0.5 or 1
    in_top = bottom + 60 * k                       # where the inner vertical begins
    span_in = ((arc_in.x - inner_x) ** 2 + (arc_in.y - in_top) ** 2) ** 0.5
    new_in = [Point(arc_in.x + tx / tl * span_in * 0.4, arc_in.y + ty / tl * span_in * 0.4, None),
              Point(inner_x, in_top + span_in * 0.4, None), Point(inner_x, in_top, "curve", smooth=True),
              Point(inner_x, bottom, "line"), Point(left, bottom, "line")]
    # the outer edge: from the cut upward it leaves vertical and arrives at arc_out along the arc's tangent
    ux, uy = arc_out.x - h_out.x, arc_out.y - h_out.y   # direction the arc travels away from the cut
    ul = (ux * ux + uy * uy) ** 0.5 or 1
    out_top = bottom + 170 * k                     # where the outer vertical ends and the curve begins
    span_out = ((arc_out.x - left) ** 2 + (arc_out.y - out_top) ** 2) ** 0.5
    new_out = [Point(left, out_top, "line"),
               Point(left, out_top + span_out * 0.45, None), Point(arc_out.x - ux / ul * span_out * 0.4, arc_out.y - uy / ul * span_out * 0.4, None)]
    # splice: replace the inner handles + inner corner + outer corner + outer handles
    a, b = j_in + 1, k_out                         # pts[a:b] are the handles, corners and handles between the two arc points
    pts[a:b] = new_in + new_out
    arc_in.smooth = True; arc_out.smooth = True
    # the dot: the exclamation's, and the stem bottom where its stem ends
    exclam = font["exclam"]
    dot = min(exclam.contours, key=lambda c: max(p.y for p in c.points))
    for c in list(glyph.contours):
        if c is not body:
            glyph.contours.remove(c)
    glyph.contours.append(copy.deepcopy(dot))
    stem_bottom = min(p.y for c in exclam.contours if c is not dot for p in c.points)
    lows = sorted({round(p.y) for p in body.points if p.y < 600})
    if lows:
        old_bottom = lows[0]
        for p in body.points:
            if abs(p.y - old_bottom) < 1:
                p.y = stem_bottom
    note("question", "Vera's hook kept, the left terminal turned down; the exclamation's dot", "toyon", "draw")


def question_terminal(font):
    if QUESTION_STYLE == "vera":
        return vera_question(font)
    """The question mark drawn from Toyon's numbers (2048 to the em, Regular):
    an arc, 821 across and 389 above the x-height, centred on the cell at 616,1120, stroke 168,
    open at the left where the arc ends in a level cut at the x-height; a neck curving out of the
    arc's lower right into a stem 170 wide centred on the cell, from 573 down to the exclamation
    mark's stem bottom; and the exclamation mark's own dot, so the gap and the dot are the same in
    both. Hack's question mark is replaced wholesale. The Bold scales the strokes with its stem."""
    import math
    from ufoLib2.objects import Point
    glyph = font["question"]
    layer = font.layers.defaultLayer
    k = weight_ratio(font)
    body = max(glyph.contours, key=lambda c: len(c.points))
    glyph.contours.remove(body)
    # the dot and the gap above it are the exclamation mark's, so the two punctuate alike: Hack's
    # question-mark dot was bigger, lower and closer to the stem than its exclamation's
    import copy
    exclam = font["exclam"]
    dot = min(exclam.contours, key=lambda c: len(c.points) if len(c.points) > 4 else 99)
    dot = min(exclam.contours, key=lambda c: max(p.y for p in c.points))
    for c in list(glyph.contours):
        glyph.contours.remove(c)
    glyph.contours.append(copy.deepcopy(dot))
    stem_bottom = min(p.y for c in exclam.contours if c is not dot for p in c.points)
    cx, cy, R = 616, 1120, 389                    # centred on the x-height, top at 1509; the terminal is the arc's end, cut level
    WIDE = 410 / 389                              # the arc an ellipse, 821 across: a circle of 778 reads tight
    stroke = 168 * k
    r = R - stroke
    K = 0.5523
    pen = glyph.getPen()
    # the outer arc, anticlockwise on the page from the left terminal over the top to the right,
    # drawn as circle segments and widened to the ellipse
    def arc(radius, a0, a1, steps):
        out = []
        for i in range(steps):
            t0 = math.radians(a0 + (a1 - a0) * i / steps); t1 = math.radians(a0 + (a1 - a0) * (i + 1) / steps)
            h = 4 / 3 * math.tan((t1 - t0) / 4) * radius
            p0 = (cx + radius * math.cos(t0), cy + radius * math.sin(t0)); p3 = (cx + radius * math.cos(t1), cy + radius * math.sin(t1))
            w = lambda pt: (cx + (pt[0] - cx) * WIDE, pt[1])
            out.append((w((p0[0] - h * math.sin(t0), p0[1] + h * math.cos(t0))), w((p3[0] + h * math.sin(t1), p3[1] - h * math.cos(t1))), w(p3)))
        return out
    # outer edge: from the terminal's outer corner (left, at the level cut) up round the top to
    # the lower right, where the neck begins
    pen.moveTo((cx - R * WIDE, cy))
    for c1, c2, p in arc(R, 180, 180 - 215, 4):      # over the top, clockwise, to 35 degrees below the right
        pen.curveTo(c1, c2, p)
    # the neck: out of the arc into the stem's right edge
    sx1 = cx + 85 * k
    pen.curveTo((cx + R * WIDE * 0.55, cy - R * 0.9), (sx1 + 20, 700), (sx1, 573))
    pen.lineTo((sx1, stem_bottom))
    pen.lineTo((cx - 85 * k, stem_bottom))
    sx0 = cx - 85 * k
    pen.lineTo((sx0, 573))
    # the inner edge of the neck back into the inner arc
    pen.curveTo((sx0, 700), (cx + r * WIDE * 0.75, cy - r * 0.95), (cx + r * WIDE * math.cos(math.radians(-35)), cy + r * math.sin(math.radians(-35))))
    for c1, c2, p in arc(r, -35, 180, 4):            # back over the top, anticlockwise, to the left
        pen.curveTo(c1, c2, p)
    pen.closePath()
    note("question", "drawn fresh: an arc, a neck, the terminal turned down", "toyon", "draw")


# The e's crossbar lifted by E_BAR_LIFT, Menlo's 46: Vera's bar sits at 516 of 2048, Menlo's at
# 562, which opens the lower aperture, the thing liked about Menlo's e. The bar is the bottom
# edge of the eye and the top edge of the aperture: the eye's lower points and the bar's
# underside move up together, the bowl's outer curve and the terminal stay.
E_BAR_LIFT = 46


def lift_e_bar(font):
    glyph = font["e"]
    outer = max(glyph.contours, key=lambda c: len(c.points))
    eye = min(glyph.contours, key=lambda c: len(c.points))
    x0 = min(p.x for p in outer.points)
    for pt in outer.points:
        if 480 < pt.y < 560 and pt.x > x0 + 150:   # the bar's underside and the aperture's corner, not the bowl's left extreme
            pt.y += E_BAR_LIFT
    bottom = min(p.y for p in eye.points)
    for pt in eye.points:
        if pt.y < bottom + 120:                    # the eye's bottom edge and the handles that curve into it
            pt.y += E_BAR_LIFT
    note("e", f"crossbar lifted {E_BAR_LIFT} to Menlo's height, opening the aperture", "m", "draw")


# The figure one's flag at Menlo's length: Menlo's 1 is Vera's with the flag's tip moved 38 left
# and about 115 down, so the flag reaches further and lower; Hack's is a steeper redraw. Applied
# to DejaVu's outline, which the picks copy in.
ONE_FLAG = (-38, -119, -109)      # the tip's shift: x, lower corner y, upper corner y


def menlo_one(font):
    glyph = font["one"]
    cap = font.info.capHeight
    pts = [p for c in glyph.contours for p in c.points if p.y > cap / 2]   # the flag is in the upper half; the foot's corners sit further left in the Bold
    left = min(p.x for p in pts)
    tip = sorted((p for p in pts if abs(p.x - left) < 1), key=lambda p: p.y)
    if len(tip) != 2:
        return
    k = weight_ratio(font)
    dx, dy0, dy1 = ONE_FLAG
    tip[0].x += dx * k; tip[0].y += dy0 * k
    tip[1].x += dx * k; tip[1].y += dy1 * k
    note("one", "the flag lengthened to Menlo's", "m", "draw")


# The chevrons thinned to CHEVRON_STROKE. Resized from Hack's 1057 by 1002 to Toyon's 911 by
# 1192, their diagonals come out about 183 across the stroke against the bar's 172; the inner
# edge moves toward the outer at the arms' ends and, by the same amount across the stroke, at
# the inner apex.
CHEVRON_STROKE = 180      # across the stroke, between the bar's 172 and the lowercase stems' 184


def thin_chevrons(font):
    """The chevrons, in order: the apex sharpened to a short flat, the chevron fitted back to
    CHEVRON_WIDTH and leaned toward what it encloses, then each arm thinned to CHEVRON_STROKE
    across and its end cut square to it, both measured from the arm's final angle so the two
    arms come out alike and the cuts are perpendicular."""
    import math
    from ufoLib2.objects import Point
    k = weight_ratio(font, "operator")
    target = CHEVRON_STROKE * k
    tip = CHEVRON_TIP * k                          # the apex flat scales with the weight too; unscaled it was a needle in the Bold
    for name in ["less", "greater"]:
        glyph = font[name]
        contour = max(glyph.contours, key=lambda c: len(c.points))
        sx = 1 if name == "less" else -1
        def geometry():
            pts = contour.points
            xs = [p.x for p in pts]
            apex_x = min(xs) if name == "less" else max(xs)
            far_x = max(xs) if name == "less" else min(xs)
            cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
            return pts, apex_x, far_x, cy
        # 1. the apex: Vera's vertical flat (198 tall) becomes a flat CHEVRON_TIP tall, further
        #    out where the outer edges would meet; a true point reads as a needle
        pts, apex_x, far_x, cy = geometry()
        apex = sorted((p for p in pts if abs(p.x - apex_x) < 1), key=lambda p: p.y)
        ends = sorted((p for p in pts if abs(p.x - far_x) < 1), key=lambda p: p.y)
        if len(apex) == 2 and len(ends) == 4:
            lo, hi = apex
            run, rise = abs(ends[3].x - hi.x), ends[3].y - hi.y
            reach = (hi.y - cy) * run / rise
            back = (tip / 2) * run / rise
            tip_x = apex_x - sx * reach + sx * back
            lo.x, lo.y = tip_x, cy - tip / 2
            hi.x, hi.y = tip_x, cy + tip / 2
        # 2. back to the width, about the far end, and leaned toward the content
        pts, apex_x, far_x, cy = geometry()
        xs = [p.x for p in pts]
        t = Transform().translate(far_x, 0).scale(CHEVRON_WIDTH / (max(xs) - min(xs)), 1).translate(-far_x, 0)
        for p in pts:
            p.x, p.y = t.transformPoint((p.x, p.y))
        xs = [p.x for p in pts]
        lean = glyph.width / 2 + sx * CHEVRON_LEAN - (max(xs) + min(xs)) / 2
        for p in pts:
            p.x += lean
        # 3. each arm thinned from the inside to the target, and its end cut square, from the
        #    arm's own final angle
        pts, apex_x, far_x, cy = geometry()
        ends = sorted((p for p in pts if abs(p.x - far_x) < 1), key=lambda p: p.y)
        apex = sorted((p for p in pts if abs(p.x - apex_x) < 1), key=lambda p: p.y)
        inner_apex = [p for p in pts if abs(p.x - apex_x) > 1 and abs(p.y - cy) < 2]
        if len(ends) != 4 or len(apex) != 2:
            continue
        for outer, inner, apex_corner, up in ((ends[3], ends[2], apex[1], 1), (ends[0], ends[1], apex[0], -1)):
            angle = math.atan(abs(outer.y - apex_corner.y) / abs(outer.x - apex_corner.x))
            vertical = abs(outer.y - inner.y)
            thin = (vertical * math.cos(angle) - target) / math.cos(angle)
            inner.y += up * thin                       # the inner edge toward the outer
            if CHEVRON_CUT == "square":
                # the inner corner stays, the outer corner goes back along the arm so the cut is
                # perpendicular to it
                outer.x = inner.x - sx * target * math.sin(angle)
                outer.y = inner.y + up * target * math.cos(angle)
            if len(inner_apex) == 1 and up == 1:
                inner_apex[0].x += -sx * thin * math.cos(angle) / math.sin(angle)
        note(name, f"the apex sharpened to a {CHEVRON_TIP} flat, fitted to {CHEVRON_WIDTH} and leaned {CHEVRON_LEAN}, the stroke {CHEVRON_STROKE} across", "toyon", "draw")


# One size for the punctuation dots. Hack's period, colon and semicolon dots are 324 to 338
# across, DejaVu's exclamation dot 203 (rounded to 229 here), Hack's question dot 292; Menlo
# sets its at 263. Every round dot in . : ; ! ? is scaled to DOT_SIZE, a dot on the baseline
# about its base so it keeps its overshoot, a raised dot about its centre; the comma, alone and
# in the semicolon, is scaled by the same factor about the baseline so its head matches.
DOT_SIZE = 324            # Hack's own size; Menlo's 263 reads too light in the app


def dot_sizes(font):
    layer = font.layers.defaultLayer
    k = weight_ratio(font, "dot")                  # read from the period before it is resized
    for name in ["period", "colon", "semicolon", "exclam", "question"]:
        glyph = font[name]
        for c in glyph.contours:
            xs = [p.x for p in c.points]; ys = [p.y for p in c.points]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if not (0.85 < w / h < 1.15 and w < 420 and not any(p.type == "line" for p in c.points)):
                continue                           # a round dot: all curves, near square, small
            cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            about = (cx, min(ys)) if min(ys) < 60 else (cx, cy)
            t = Transform().translate(*about).scale(DOT_SIZE * k / w).translate(-about[0], -about[1])
            for pt in c.points:
                pt.x, pt.y = t.transformPoint((pt.x, pt.y))
        note(name, f"the dot set to {DOT_SIZE}, one size for the punctuation dots", "toyon", "draw")
    factor = DOT_SIZE / 324
    for name in ["comma", "semicolon"]:
        glyph = font[name]
        for c in glyph.contours:
            xs = [p.x for p in c.points]; ys = [p.y for p in c.points]
            if max(ys) - min(ys) < 400 and not any(p.type == "line" for p in c.points):
                continue                           # the semicolon's dot, already done
            cx = (max(xs) + min(xs)) / 2
            t = Transform().translate(cx, 0).scale(factor).translate(-cx, 0)
            for pt in c.points:
                pt.x, pt.y = t.transformPoint((pt.x, pt.y))
        note(name, f"the comma scaled with the dots, by {factor:.2f} about the baseline", "toyon", "draw")


def question_dot(font):
    """The question mark punctuated like the exclamation mark: its dot is the exclamation's, and
    its stem ends where the exclamation's does, so the gap over the dot is the same in both.
    Vera's question stem runs down to 401 against the exclamation's 481, and once the dot is
    sized up about its base the two gaps are 64 and 144. Toyon's own question mark is drawn
    this way already; this is what makes a DejaVu copy match. Runs after dot_sizes."""
    import copy
    glyph, exclam = font["question"], font["exclam"]
    dot = min(exclam.contours, key=lambda c: max(p.y for p in c.points))
    body = max(glyph.contours, key=lambda c: len(c.points))
    for c in list(glyph.contours):
        if c is not body:
            glyph.contours.remove(c)
    glyph.contours.append(copy.deepcopy(dot))
    stem_bottom = min(p.y for c in exclam.contours if c is not dot for p in c.points)
    old_bottom = min(p.y for p in body.points)
    for p in body.points:
        if abs(p.y - old_bottom) < 1:
            p.y = stem_bottom
    note("question", "the exclamation mark's dot, and its stem ended where the exclamation's ends", "toyon", "draw")


# The multiplication sign drawn fresh: two bars of the chevrons' stroke crossing at 45 degrees,
# centred on the operator line, in a box CROSS_BOX square. Scaling Hack's cross down to that
# box thins its stroke to 150, so it is drawn rather than scaled. fontmake's overlap removal
# merges the two bars.
CROSS_BOX = 843


def draw_cross(font):
    import math
    glyph = font["multiply"]
    bx0, _, bx1, _ = bounds(font["bar"], font.layers.defaultLayer)
    t = CHEVRON_STROKE * weight_ratio(font, "operator")
    for c in list(glyph.contours):
        glyph.contours.remove(c)
    cx, cy = glyph.width / 2, OPERATOR_LINE
    L = CROSS_BOX * math.sqrt(2) - t              # a bar this long at 45 degrees spans the box
    pen = glyph.getPen()
    for angle in (45, -45):
        a = math.radians(angle)
        dx, dy = math.cos(a), math.sin(a)         # along the bar
        nx, ny = -dy, dx                           # across it
        corners = [(cx - dx * L / 2 - nx * t / 2, cy - dy * L / 2 - ny * t / 2),
                   (cx + dx * L / 2 - nx * t / 2, cy + dy * L / 2 - ny * t / 2),
                   (cx + dx * L / 2 + nx * t / 2, cy + dy * L / 2 + ny * t / 2),
                   (cx - dx * L / 2 + nx * t / 2, cy - dy * L / 2 + ny * t / 2)]
        pen.moveTo(corners[0])
        for pt in corners[1:]:
            pen.lineTo(pt)
        pen.closePath()
    note("multiply", f"drawn as two bars of {CHEVRON_STROKE} crossing at 45 degrees in a {CROSS_BOX} box", "toyon", "draw")


# The N at Menlo's width: Vera's is 955 across, Menlo's 1075, extended to the left. The left stem
# and the top of the diagonal move out by N_WIDEN; the right stem stays, so the stems keep their
# weight and the diagonal flattens a little.
N_WIDEN = 120


def widen_n(font):
    glyph = font["N"]
    xs = [p.x for c in glyph.contours for p in c.points]
    mid = (min(xs) + max(xs)) / 2
    for c in glyph.contours:
        for pt in c.points:
            if pt.x < mid:
                pt.x -= N_WIDEN * weight_ratio(font)
    note("N", f"widened {N_WIDEN} to the left, to Menlo's width", "m", "draw")


# Toyon's own rules, applied whatever is picked, like the enclosure span: the asterisk on the
# operator line, the slashed zero, round tittles, the lifted crossbars, the quotes at Menlo's
# weight, the question mark, the e's bar, the chevrons, the dots, the cross, the N.
ASTERISK_WIDTH = 1060     # near Menlo's 1119; the chevrons' 911 is too small
CHEVRON_HEIGHT = 1192     # taller than the family's 1002, so more open; 1300 reads as a billboard
CHEVRON_LEAN = 21         # placed off centre toward what they enclose: < to the right, > to the left
CHEVRON_WIDTH = 911       # narrower than the family's 1057
CHEVRON_CUT = "square"    # the arms' ends cut perpendicular to the arm, like the cross's; "vertical" is Vera's upright cut
CHEVRON_TIP = 172         # the apex's flat, the hyphen's thickness, so <- and -> meet stroke to stroke

ALWAYS = [low_asterisk, slashed_zero, round_tittles, lift_cap_bars, menlo_quotes, question_terminal, lift_e_bar, menlo_one, thin_chevrons, dot_sizes, question_dot, draw_cross, widen_n]
PICK_OFF = {question_terminal: "?"}     # a rule a "dv" pick on its character switches off: the glyph is then DejaVu's, copied in
MOVES = {"toyon": {"_": underscore_on_baseline, "<": box("less", CHEVRON_WIDTH, CHEVRON_HEIGHT, OPERATOR_LINE), ">": box("greater", CHEVRON_WIDTH, CHEVRON_HEIGHT, OPERATOR_LINE),
                   "\u00d7": lambda font: None, "?": lambda font: None, "t": hooked_t}}   # the cross is drawn by its rule whatever is picked, the question mark by its unless picked "dv"
NAMES = {"dv": "DejaVu", "toyon": "Toyon", "hk": "Hack", "m": "Menlo"}


def picks():
    if not PICKS.exists():
        return {}
    return json.loads(PICKS.read_text()).get("picks", {})


def apply_picks(font, dejavu, chosen):
    names = by_unicode(font)
    copies, hand = [], []
    for ch, face in sorted(chosen.items()):
        if face == "hk" or len(ch) != 1 or ord(ch) not in names:
            continue
        if face == "dv":
            copies.append(names[ord(ch)])
        elif ch in MOVES.get(face, {}):
            MOVES[face][ch](font)
        else:
            hand.append((ch, face))
    if copies:
        copy_from_dejavu(font, dejavu, copies)
    return copies, hand


def forge(style):
    LINEAGE.clear()                                # one weight's record at a time; the Regular's is the one written
    spec = WEIGHTS[style]
    font = ufoLib2.Font.open(HACK / "source" / f"Hack-{style}.ufo")
    dejavu = TTFont(REF / spec["dejavu"])
    rename(font, style)
    chosen = picks()
    copies, hand = apply_picks(font, dejavu, chosen)
    moved = [ch for ch, f in chosen.items() if ch in MOVES.get(f, {})]
    off = [ch for ch, f in chosen.items() if f != "hk"]
    print(f"    {style}: {len(chosen)} picked, {len(off)} off Hack"
          + (f", copied from DejaVu {' '.join(copies)}" if copies else "")
          + (f", moved {' '.join(moved)}" if moved else ""))
    for ch, face in hand:
        print(f"      by hand, still Hack's: {ch} picked from {NAMES[face]}")
    for change in ALWAYS:
        if chosen.get(PICK_OFF.get(change)) == "dv":
            continue
        change(font)
    span_enclosures(font)
    operator_widths(font)
    ligatures(font, chosen)
    ufo = WORK / f"ToyonMono-{style}.ufo"
    if ufo.exists():
        shutil.rmtree(ufo)
    font.save(ufo)
    return ufo


def build(ufo, style):
    ttf_dir = WORK / "ttf"
    ttf_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "fontmake", "-u", str(ufo), "-o", "ttf",
                    "--output-dir", str(ttf_dir), "--no-production-names"], check=True)
    ttf = ttf_dir / f"ToyonMono-{style}.ttf"
    f = TTFont(ttf)
    f["OS/2"].fsType = 0
    f.flavor = "woff2"
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"toyon-mono-{WEIGHTS[style]['file']}.woff2"
    f.save(out)
    shutil.copy(ttf, OUT / f"ToyonMono-{style}.ttf")
    return out


LINEAGE_FILE = ROOT / "build" / "lineage.json"   # the build's record of what it did to each glyph


def write_lineage():
    """The lineage per character: the base first (Vera's drawing, or Hack's redraw), then every
    step the Regular build recorded, in order. Only the Regular's steps are kept; the Bold's are
    the same list."""
    font = ufoLib2.Font.open(WORK / "ToyonMono-Regular.ufo")
    chars = {}
    for g in font:
        if not g.unicodes:
            continue
        u = g.unicodes[0]
        if not (33 <= u < 127 or u == 0xD7):
            continue
        redrawn = chr(u) in HACK_REDREW
        base = {"step": "Hack's redraw of Vera's", "from": "hk"} if redrawn else {"step": "Vera's drawing, as DejaVu has it", "from": "dv"}
        steps = LINEAGE.get(g.name, [])
        # a DejaVu copy supersedes Hack's redraw as the base; on a glyph Hack never redrew it changes nothing
        if steps and steps[0]["from"] == "dv":
            if redrawn:
                base = {"step": "Vera's drawing, DejaVu's outline copied in over Hack's redraw", "from": "dv"}
            steps = steps[1:]
        chars[chr(u)] = [base] + steps
    for seq, (name, _, _, _) in LIGS.items():
        if name in font:
            chars[seq] = [{"step": "a ligature glyph the build composes from Hack's sign", "from": "toyon"}]
    LINEAGE_FILE.write_text(json.dumps(chars, ensure_ascii=False, sort_keys=True, indent=0) + "\n")
    print(f"    {LINEAGE_FILE.name}: {sum(1 for v in chars.values() if len(v) > 1)} glyphs with steps beyond their base")


def main():
    styles = sys.argv[1:] or list(WEIGHTS)
    WORK.mkdir(parents=True, exist_ok=True)
    for style in styles:
        ufo = forge(style)
        out = build(ufo, style)
        print(f"    {out.relative_to(ROOT)}  ({out.stat().st_size // 1024} KB)")
        if style == "Regular":                     # recorded before the Bold's steps overwrite the record
            write_lineage()


if __name__ == "__main__":
    main()
