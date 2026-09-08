"""
Stop shipping React and the web fonts inside every page; load them from a CDN.

--- The problem ---

Every page in public/ is a self-contained archive (see tools/bundle.py for the
full explanation). Self-contained is lovely -- the file renders with no
internet at all -- but it means each page carries its own private copy of
things that are identical across all seven pages:

  * React + ReactDOM      ~61KB per page, byte-identical in all seven
  * Manrope, Schibsted Grotesk, Space Grotesk
                          8 to 11 woff2 font files, ~185-248KB per page

That is roughly 1.9MB of duplicated bytes across the site. Worse, a visitor
who reads three case studies downloads three separate copies of React and
three separate copies of the same fonts, because nothing tells the browser
they are the same file.

--- The fix, and why it is so small ---

The obvious approach would be to hand-edit script tags. We do not have to,
because the bundle format already anticipated this.

REACT. The exporter records a note in the ext_resources section saying
"this asset is really https://unpkg.com/react@18.3.1/...". At page load, the
loader turns those notes into a lookup table at window.__resources, and the
Claude Design runtime asks that table for React:

    function cdnScriptFor(url, sri) {
      const res = window.__resources;
      const v = res ? res[url] : void 0;
      return typeof v === "string" && v ? { src: v } : { src: url, integrity: sri };
    }

Read the last line: on a *miss*, it loads the real CDN URL with an integrity
hash it already knows. So the entire change is to delete React from the
bundle. The runtime's existing fallback does the rest, SRI included.

(SRI -- Subresource Integrity -- is that integrity="sha384-..." attribute. It
is a fingerprint of the expected file. If the CDN ever served something else,
the browser would refuse to run it. It is what makes loading code from someone
else's server reasonable.)

FONTS. The pages currently carry a large <style> block of @font-face rules
pointing at bundled woff2 files. Those rules originally came from Google
Fonts -- the pages still have the <link rel="preconnect"> tags that prove it.
We delete the font files and swap that <style> block for the ordinary Google
Fonts <link> it was generated from. The runtime mounts any <link> it does not
have a bundled copy of, so it just works.

--- The tradeoff ---

The pages stop being self-contained. They now need the network, and if unpkg
is down the page will not render at all, because the runtime needs React
before it can draw anything. For a portfolio on the public web that is a good
trade -- smaller pages, and a browser cache shared across all seven. It would
be the wrong trade if you needed to hand someone a single file that works on
a plane.

Run it from the repo root:

    python3 tools/externalize_assets.py
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle  # noqa: E402

# Google Fonts serves variable fonts, so a whole weight range costs one file.
GOOGLE_FONTS = 'https://fonts.googleapis.com/css2?%s&display=swap'


def google_fonts_url(families):
    """Build a Google Fonts URL from {family: {weights}} taken off the page."""
    parts = []
    for family in sorted(families):
        weights = sorted(families[family], key=int)
        axis = weights[0] if len(weights) == 1 else '%s..%s' % (weights[0], weights[-1])
        parts.append('family=%s:wght@%s' % (family.replace(' ', '+'), axis))
    return GOOGLE_FONTS % '&'.join(parts)


for path in sorted(glob.glob('public/*.html')):
    b = bundle.load(path)
    before = os.path.getsize(path)

    # --- 1. Drop React -------------------------------------------------------
    # ext_resources is the list of "this UUID is really that URL" notes. Every
    # entry in it is by definition something fetchable from the network, so
    # every entry can go. Today that is exactly React and ReactDOM.
    react_uuids = [e['uuid'] for e in b['ext']]
    react_urls = [e['id'] for e in b['ext']]
    for uuid in react_uuids:
        b['manifest'].pop(uuid, None)
    b['ext'] = []

    # --- 2. Drop the bundled fonts ------------------------------------------
    font_uuids = [u for u, a in b['manifest'].items() if a['mime'].startswith('font/')]

    # --- 3. Swap the @font-face block for a Google Fonts link ---------------
    # The page has two <style> blocks: the first is nothing but @font-face
    # rules, the second is the real page CSS. Only the first one goes.
    template = b['template']
    style_blocks = list(re.finditer(r'<style>(.*?)</style>', template, re.S))
    font_block = next((m for m in style_blocks if '@font-face' in m.group(1)), None)
    if font_block is None:
        raise SystemExit('%s: no @font-face block found' % path)

    families = {}
    for face in re.findall(r'@font-face \{(.*?)\}', font_block.group(1), re.S):
        family = re.search(r"font-family: '([^']+)'", face).group(1)
        weight = re.search(r'font-weight: (\d+)', face).group(1)
        families.setdefault(family, set()).add(weight)

        # These pages use no italics. If that ever changes, the URL builder
        # needs an ital axis, so fail loudly rather than silently dropping it.
        if re.search(r'font-style: (?!normal)', face):
            raise SystemExit('%s: italic face found, URL builder needs updating' % path)

    link = '<link rel="stylesheet" href="%s">' % google_fonts_url(families)
    template = template[:font_block.start()] + link + template[font_block.end():]

    for uuid in font_uuids:
        b['manifest'].pop(uuid, None)

    # --- 4. Check we did not orphan anything --------------------------------
    # If a UUID we deleted is still referenced in the markup, the loader would
    # leave the raw UUID in place and the browser would request a file that
    # does not exist. Catch that here instead of in the browser.
    for uuid in react_uuids + font_uuids:
        if uuid in template:
            raise SystemExit('%s: removed asset %s is still referenced' % (path, uuid))

    b['template'] = template
    bundle.save(path, b)

    after = os.path.getsize(path)
    print('  %-22s %6.0fKB -> %6.0fKB  (-%.0fKB)  react=%d fonts=%d  %s' % (
        os.path.basename(path), before / 1024, after / 1024,
        (before - after) / 1024, len(react_uuids), len(font_uuids),
        ', '.join('%s %s' % (f, min(w, key=int) + '-' + max(w, key=int))
                  for f, w in sorted(families.items()))))

print('\nReact now loads from: %s' % '\n                      '.join(react_urls))
