"""
Read and write the data sections of a Claude Design bundled HTML export.

--- What is a "bundled export"? ---

Each file in public/ looks like one HTML page, but it is really a tiny
self-extracting archive. Open one in a text editor and you'll find three
<script> tags near the bottom that hold data rather than code:

  <script type="__bundler/manifest">      every image, font and JS file,
                                          gzipped and base64-encoded, each
                                          filed under a random UUID

  <script type="__bundler/ext_resources"> a list saying "this UUID is really
                                          https://unpkg.com/react@18.3.1/..."

  <script type="__bundler/template">      the actual page HTML, stored as a
                                          JSON string. Images are referenced
                                          by UUID: <img src="e21a68ac-...">

When the page loads, the small loader script at the top decodes every asset
into a blob: URL, swaps each UUID in the template for its blob URL, and
replaces the live document with the result. That is why the page shows
"Unpacking..." for a moment before anything appears.

That design makes the file portable -- it renders with no network at all --
but it also means you cannot edit the page with a normal find-and-replace:
the markup lives inside a JSON string, and the assets are base64 blobs.
This module gives you the page as ordinary Python data instead.

--- Usage ---

    import bundle
    b = bundle.load('public/vela.html')

    b['template']   # str  -- the page HTML
    b['manifest']   # dict -- {uuid: {mime, compressed, data}}
    b['ext']        # list -- [{id: <url>, uuid: <uuid>}]

    b['template'] = b['template'].replace('old.html', 'new.html')
    bundle.save('public/vela.html', b)

--- Why the fussy encoding rules in save() ---

save() reproduces the exporter's own JSON formatting exactly, so that loading
a file and saving it straight back is byte-for-byte identical. That property
is worth protecting: it means any diff you see in git is a change you made on
purpose, not encoding noise from the round trip. There is a test for it in
tools/test_roundtrip.py.
"""
import json
import re

# Each section is captured in three parts so we can rewrite only the JSON
# payload (group 2) and leave the surrounding tags and whitespace untouched.
SECTIONS = {
    'manifest': re.compile(r'(<script type="__bundler/manifest">\s*)(.*?)(\s*</script>)', re.S),
    'ext':      re.compile(r'(<script type="__bundler/ext_resources">\s*)(.*?)(\s*</script>)', re.S),
    'template': re.compile(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)', re.S),
}


def load(path):
    """Parse a bundled export into a dict of plain Python values."""
    raw = open(path, encoding='utf-8').read()
    out = {'_raw': raw}
    for name, rx in SECTIONS.items():
        match = rx.search(raw)
        if not match:
            raise SystemExit('%s: missing __bundler/%s section' % (path, name))
        out[name] = json.loads(match.group(2))
    return out


def save(path, bundle):
    """Write a bundle back out, matching the exporter's encoding exactly."""
    raw = bundle['_raw']
    for name, rx in SECTIONS.items():
        # Re-search each pass: an earlier replacement shifts later offsets.
        match = rx.search(raw)

        # separators=(',', ':') -- the exporter writes compact JSON with no
        # spaces after commas or colons.
        # ensure_ascii=False    -- it leaves characters like the em dash and
        #                          the arrows in the page text as real UTF-8
        #                          rather than \uXXXX escapes.
        body = json.dumps(bundle[name], ensure_ascii=False, separators=(',', ':'))

        # The JSON sits *inside* a <script> tag, so a literal "</" anywhere in
        # it (the page HTML is full of closing tags) would end that script tag
        # early and corrupt the file. Escaping the slash as / keeps the
        # JSON meaning identical while making the sequence invisible to the
        # HTML parser. The exporter does the same thing.
        body = body.replace('</', '<\\u002F')

        raw = raw[:match.start(2)] + body + raw[match.end(2):]
    open(path, 'w', encoding='utf-8').write(raw)
