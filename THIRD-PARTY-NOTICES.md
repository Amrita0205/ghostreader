# Third party notices

GhostRead's own source code is MIT licensed. See [LICENSE](LICENSE).

GhostRead depends on the following third party packages. When you install
GhostRead with `pip`, these are downloaded separately from PyPI under their own
licences. When you download the prebuilt `GhostRead.exe` from the releases page,
they are **bundled inside that binary**, which has licence consequences worth
being explicit about.

## PyMuPDF — AGPL-3.0

<https://github.com/pymupdf/PyMuPDF>

PyMuPDF and the MuPDF library underneath it are licensed under the GNU Affero
General Public License v3.0. This is a copyleft licence.

**What that means here.** GhostRead's source files are MIT and stay MIT. But the
prebuilt `GhostRead.exe` is a combined work that contains PyMuPDF, so that
binary as a whole is distributed under the terms of the AGPL-3.0. Anyone who
receives the `.exe` is entitled to the complete corresponding source code.

That obligation is satisfied by this repository: every release binary is built
by GitHub Actions from a public, tagged commit, and each release page links back
to the exact source it was built from. If you redistribute the `.exe` yourself,
you must carry the same offer of source with it.

If you want a build without the copyleft obligation, you would need to replace
PyMuPDF with a permissively licensed renderer such as
[pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (Apache-2.0 / BSD-3).
All PDF work is isolated in `ghostread/document.py`, so that is a contained
change rather than a rewrite.

## Pillow — MIT-CMU

<https://github.com/python-pillow/Pillow>

Permissive. No obligations beyond retaining the copyright notice.

## Python and Tcl/Tk

The prebuilt binary also embeds the CPython runtime (PSF License) and Tcl/Tk
(BSD-style). Both are permissive.
