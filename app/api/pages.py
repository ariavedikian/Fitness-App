"""Routes that serve HTML pages.

Pages are shells: they carry only the chrome (nav, who is signed in) and let
JavaScript fetch feature data from ``/api``. That keeps one source of truth
for data and lets the same endpoints serve a future mobile client.

Excluded from the OpenAPI schema so ``/docs`` stays a description of the API
rather than a list of web pages.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.api.deps import get_optional_user
from app.core.templates import templates
from app.models import User

router = APIRouter(tags=["pages"], include_in_schema=False)

# 302: "look over here instead", and the browser keeps using GET.
REDIRECT = 302


@router.get("/", response_class=HTMLResponse)
def home(user: User | None = Depends(get_optional_user)) -> Response:
    return RedirectResponse("/dashboard" if user else "/login", REDIRECT)


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request, user: User | None = Depends(get_optional_user)
) -> Response:
    if user is not None:
        return RedirectResponse("/dashboard", REDIRECT)
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request, user: User | None = Depends(get_optional_user)
) -> Response:
    if user is not None:
        return RedirectResponse("/dashboard", REDIRECT)
    return templates.TemplateResponse(request, "register.html", {"user": None})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request, user: User | None = Depends(get_optional_user)
) -> Response:
    # The redirect is a courtesy for the visitor, not the security boundary:
    # the data itself is guarded by get_current_user on the /api routes.
    if user is None:
        return RedirectResponse("/login", REDIRECT)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request, user: User | None = Depends(get_optional_user)
) -> Response:
    if user is None:
        return RedirectResponse("/login", REDIRECT)
    return templates.TemplateResponse(request, "profile.html", {"user": user})


@router.get("/foods", response_class=HTMLResponse)
def foods_page(
    request: Request, user: User | None = Depends(get_optional_user)
) -> Response:
    if user is None:
        return RedirectResponse("/login", REDIRECT)
    return templates.TemplateResponse(request, "foods.html", {"user": user})
