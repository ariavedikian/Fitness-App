"""Serving ``/static`` so browsers never run a stale copy of a changed file.

Starlette's ``StaticFiles`` sends ``ETag`` and ``Last-Modified`` but no
``Cache-Control``, which leaves browsers to guess how long a file stays
fresh ("heuristic freshness", typically a tenth of the time since it last
changed) and to reuse it without asking — so an edited script could keep
running in its old form for hours or days.

``Cache-Control: no-cache`` doesn't mean "don't cache": it means "store it,
but check before each use". The browser sends the ``ETag`` back, an unchanged
file costs a bodiless ``304 Not Modified``, and a changed one is always
fetched. That covers ES-module imports inside our scripts too (``import
"./api.js"``), which versioned URLs (``app.js?v=…``) wouldn't reach without
an import map rewriting every one. Long-lived caching of content-hashed files
would save the revalidation requests, but needs a build step this
no-build-step frontend deliberately doesn't have.
"""

from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class RevalidatedStaticFiles(StaticFiles):
    """``StaticFiles`` whose responses must be revalidated before reuse."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        # Set on the 304 as well as the 200, so the rule survives revalidation.
        response.headers["Cache-Control"] = "no-cache"
        return response
