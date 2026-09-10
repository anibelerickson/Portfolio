"""
Repoint the site's internal links at the filenames that actually exist.

--- The bug ---

These pages were first exported from Claude Design under their display names,
so the homepage was "Anibel Erickson.dc.html" and the case studies were
"VELA.dc.html", "Pool Website.dc.html" and so on. Later the files were renamed
to web-friendly slugs -- lowercase, hyphens instead of spaces, and index.html
for the homepage, which is the filename every web server looks for by default.

The homepage's own links were updated to the new names. The six case study
pages were not. Every "All work" and "Next project" link still pointed at a
file that no longer existed, so clicking one produced a 404. You could get
from the homepage into a case study, but never back out.

(In an href, a space has to be written as %20 -- that is why the old links
look like "Anibel%20Erickson.dc.html". Spaces in filenames are legal but
awkward on the web, which is a good reason the rename happened.)

--- The fix ---

Swap each old filename for its current one, inside the page markup that lives
in the bundle's template section. See tools/bundle.py for why the markup needs
decoding first instead of a plain find-and-replace on the file.

Run it from the repo root:

    python3 tools/fix_internal_links.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle  # noqa: E402

RENAMES = {
    'Anibel%20Erickson.dc.html': 'index.html',
    'Ad%20Studio.dc.html':       'ad-studio.html',
    'Daily%20Journal.dc.html':   'daily-journal.html',
    'FADV%20Database.dc.html':   'fadv-database.html',
    'Maison%20Margiela.dc.html': 'maison-margiela.html',
    'Pool%20Website.dc.html':    'pool-website.html',
    'VELA.dc.html':              'vela.html',
}

for path in sorted(glob.glob('public/*.html')):
    b = bundle.load(path)
    template = b['template']

    replaced = {}
    for old, new in RENAMES.items():
        # Match on 'href="<name>' rather than the bare filename so we only
        # touch real links. The trailing quote is deliberately left off: some
        # links carry a fragment, as in href="index.html#work".
        count = template.count('href="%s' % old)
        if count:
            template = template.replace('href="%s' % old, 'href="%s' % new)
            replaced[old] = count

    if not replaced:
        print('  --   %s (nothing to change)' % os.path.basename(path))
        continue

    # If any .dc.html link survived, RENAMES is missing an entry -- stop rather
    # than write out a page with a link we know is broken.
    assert '.dc.html' not in template, '%s: unmapped .dc.html link remains' % path

    b['template'] = template
    bundle.save(path, b)
    print('  ->   %s: %s' % (
        os.path.basename(path),
        ', '.join('%s (%d)' % (old, n) for old, n in sorted(replaced.items()))))
