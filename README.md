# Toyon Mono

The monospaced face of the Toyon app. It is Hack, which is DejaVu Sans Mono, which is
Bitstream Vera Sans Mono, with Toyon's own choices applied by a script to Hack's sources, so
that every choice is a number and a build, not a drawing kept in an editor.

`fonts/` holds the result, Regular and Bold, as TTF and woff2. `./build.sh` rebuilds them from
scratch: it clones Hack 3.003, fetches DejaVu Sans Mono 2.37, makes a Python environment with
fontmake, and runs `tools/forge.py`.

## What the build does to Hack

Hack is DejaVu Sans Mono with 31 ASCII glyphs redrawn for code. Toyon starts from Hack and, in
order:

1. renames the font and carries Hack's, DejaVu's and Bitstream's notices in its name table;
2. applies `picks.json`, one face per glyph: `dv` copies DejaVu's outline in over Hack's redraw,
   `toyon` applies Toyon's own position or drawing to Hack's glyph, and a glyph absent from the
   file is Hack's;
3. applies its own rules, whatever is picked:
   - every operator on one line, 700 of 2048, and the enclosures `( ) [ ] { } | / \` on one span,
     -190 to 1590, centred on that same line, so a chevron's tip, a hyphen and a brace's point
     meet; and, when picked Toyon's, the brace's point taken in by 60 and its hooks longer by
     the same, so it holds its own beside Hack's wide bracket (`picks.json` picks it);
   - the hyphen, equals, plus and en dash at one width, 1000, and the hyphen and dashes at the
     stem's stroke; the plus square; the equals spread to Menlo's spacing; the underscore on the
     baseline at the operator width and Vera's thinner stroke;
   - the chevrons narrower and taller than the family's, 911 by 1192, leaned toward what they
     enclose, sharpened to a flat the hyphen's thickness, cut square at the ends and thinned to
     the operator stroke; the cross at the family's size, 933, drawn fresh as two bars of the
     plus's stroke; the asterisk at 1119, Menlo's size, its hub on the line;
   - the maths signs beyond ASCII on the same rule, which Vera and every face after it leave
     wider and lower: the minus and the division sign at the operator width and line, the
     division sign's dots round, the plus-minus at that width, the not-equal sign as the equals
     with a slash through it, and `≤ ≥` drawn as their ligatures are;
   - the colon's two dots kept a dot apart in both weights;
   - a zero slashed as Menlo's is, the slash ending inside the ring; round tittles on i and j;
     one size for the punctuation dots, with the commas scaled to match; the question mark,
     whoever drew it, punctuated like the exclamation mark,
     with its dot and its stem ending where the exclamation's does, and when picked Toyon's drawn
     as an arc with its terminal turned down (`picks.json` picks DejaVu's);
   - the crossbars of `B E F H` and the `e` lifted to Menlo's height, which opens the `e`;
   - the quote marks, straight and curly, at Menlo's weight; the `1` with Menlo's longer flag;
     the `N` at Menlo's width;
   - inside the word toyon, a `t` with its top cut on a slant and its tail rising, by a
     contextual rule; every other `t` is Vera's;
4. adds the ligatures `<= >=` (a chevron with a bar parallel to its lower arm) and `-> <-`, and
   the kern rules that draw `|| //` closer without changing any advance (`!=` has one too,
   which `picks.json` switches off);
5. builds with fontmake and writes `fonts/`.

Each number has a comment in `tools/forge.py` saying what it does and where it came from. The
research behind the choices, the review pages, the votes and the measurements, lives in the
`toyon-mono` repository.

## Weights

Hack has Regular and Bold and its masters do not interpolate, so there are two weights. An app
asking for 500 or 600 gets whatever its text engine does with 400 and 700. Every rule scales
its strokes for the Bold by Hack's own Bold ratio for that family of glyph, read from the
sources: letters 1.53, operators 1.38, dots 1.09, quotes 1.47.

## Licence

See `LICENSE.md`: the Toyon modifications are MIT; Hack is MIT; DejaVu's changes are public
domain; Bitstream Vera Sans Mono is under the Bitstream Vera licence, which is why the font is
not called Hack or Vera.
