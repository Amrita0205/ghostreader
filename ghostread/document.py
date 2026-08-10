"""PDF loading and page rendering.

This module deliberately contains no GUI code. Everything here can be
imported and tested without a display, which makes debugging much easier
when something goes wrong with rendering.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

try:
    import pymupdf
except ImportError:  # older installs still expose the library as "fitz"
    import fitz as pymupdf

from PIL import Image, ImageOps


class PdfError(Exception):
    """Raised for anything the user needs to be told about in plain English."""


class PdfDocument:
    """A thin wrapper over PyMuPDF with a small render cache.

    Rendering is thread safe, so a background thread can pre-render the next
    page while the main thread stays responsive.
    """

    def __init__(self, path, password: str | None = None, cache_size: int = 10):
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise PdfError("No such file: {}".format(self.path))
        if self.path.suffix.lower() != ".pdf":
            # PyMuPDF also reads epub, xps, cbz and so on, so this is a warning
            # rather than a hard stop.
            pass

        try:
            self.doc = pymupdf.open(str(self.path))
        except Exception as exc:
            raise PdfError("Could not open {}: {}".format(self.path.name, exc))

        if self.doc.needs_pass:
            if not password or not self.doc.authenticate(password):
                raise PdfError(
                    "{} is password protected. Pass the password with "
                    "--password.".format(self.path.name)
                )

        if self.doc.page_count == 0:
            raise PdfError("{} has no pages.".format(self.path.name))

        self.cache_size = cache_size
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ info

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page_size(self, index: int):
        """Page width and height in PDF points."""
        rect = self.doc[self.clamp(index)].rect
        return rect.width, rect.height

    def clamp(self, index: int) -> int:
        return max(0, min(int(index), self.page_count - 1))

    def zoom_for_width(self, index: int, target_px: int) -> float:
        width, _ = self.page_size(index)
        if width <= 0:
            return 1.0
        return max(0.1, float(target_px) / width)

    def zoom_for_page(self, index: int, target_w: int, target_h: int) -> float:
        width, height = self.page_size(index)
        if width <= 0 or height <= 0:
            return 1.0
        return max(0.1, min(float(target_w) / width, float(target_h) / height))

    def toc(self):
        """Outline as a list of (level, title, page_index) tuples."""
        try:
            raw = self.doc.get_toc(simple=True)
        except Exception:
            return []
        out = []
        for entry in raw:
            if len(entry) >= 3:
                level, title, page = entry[0], entry[1], entry[2]
                if page and page > 0:
                    out.append((int(level), str(title), int(page) - 1))
        return out

    # ----------------------------------------------------------------- render

    def render(self, index: int, zoom: float, invert: bool = False) -> Image.Image:
        """Render one page to a PIL image. Results are cached."""
        index = self.clamp(index)
        zoom = round(max(0.1, min(float(zoom), 8.0)), 3)
        key = (index, zoom, bool(invert))

        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit

            matrix = pymupdf.Matrix(zoom, zoom)
            pix = self.doc[index].get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            if invert:
                image = ImageOps.invert(image)

            self._cache[key] = image
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return image

    def drop_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # ----------------------------------------------------------------- search

    def search(self, term: str, start: int = 0, wrap: bool = True, limit: int = 400):
        """Find a phrase across the document.

        Returns a list of (page_index, [rects]) in reading order, beginning at
        `start` so that "find next" behaves the way people expect.
        """
        term = (term or "").strip()
        if not term:
            return []

        order = list(range(self.clamp(start), self.page_count))
        if wrap:
            order += list(range(0, self.clamp(start)))

        results = []
        with self._lock:
            for page_index in order:
                try:
                    rects = self.doc[page_index].search_for(term)
                except Exception:
                    rects = []
                if rects:
                    results.append((page_index, [tuple(r) for r in rects]))
                if len(results) >= limit:
                    break
        return results

    def page_text(self, index: int) -> str:
        return self.doc[self.clamp(index)].get_text()

    # ------------------------------------------------------------------ close

    def close(self) -> None:
        try:
            self.doc.close()
        except Exception:
            pass
        self.drop_cache()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
