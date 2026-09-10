"""
Safety net for tools/bundle.py.

Loading a bundled export and saving it straight back -- with no edits in
between -- must produce a byte-for-byte identical file. If that ever stops
being true, then every script built on bundle.py is quietly rewriting parts
of the page it was never asked to touch, and git diffs stop being trustworthy.

Run it from the repo root:

    python3 tools/test_roundtrip.py
"""
import glob
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle  # noqa: E402

failures = 0
for path in sorted(glob.glob('public/*.html')):
    original = open(path, 'rb').read()

    # Work on a copy so a bug here can never damage the real page.
    tmp = tempfile.mktemp(suffix='.html')
    shutil.copy(path, tmp)
    bundle.save(tmp, bundle.load(tmp))
    result = open(tmp, 'rb').read()
    os.unlink(tmp)

    identical = original == result
    failures += not identical
    print('%s %s (%d bytes)' % ('  ok  ' if identical else ' FAIL ',
                                os.path.basename(path), len(original)))

print('\n%d file(s) failed the round trip' % failures)
sys.exit(1 if failures else 0)
