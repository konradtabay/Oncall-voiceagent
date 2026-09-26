"""FastAPI routes and Twilio signature helpers."""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request, Response

from oncall.telephony.service import BadSignature, Telephony

router = APIRouter()

_telephony: Telephony | None = None
_auth_token: str | None = None
_public_base_url: str | None = None


def bind(
    telephony: Telephony,
    auth_token: str | None = None,
    *,
    public_base_url: str | None = None,
) -> None:
    """Attach a Telephony instance for the module-level router."""
    global _telephony, _auth_token, _public_base_url
    _telephony = telephony
    _auth_token = auth_token if auth_token is not None else telephony.validator
    base = (public_base_url or "").strip().rstrip("/")
    _public_base_url = base or None


def twilio_validation_url(request: Request) -> str:
    """URL Twilio signed: public HTTPS base behind a tunnel, query string included."""
    path = request.url.path
    query = request.url.query
    if _public_base_url:
        url = f"{_public_base_url}{path}"
    else:
        url = str(request.url).split("?")[0]
    if query:
        url = f"{url}?{query}"
    return url


def signature_ok(
    url: str,
    params: dict,
    signature: str,
    token: str | None,
) -> bool:
    """Validate ``X-Twilio-Signature`` when an auth token is configured."""
    if not token:
        return True
    from twilio.request_validator import RequestValidator

    return RequestValidator(token).validate(url, params, signature)


def reject_bad_signature() -> Response:
    """HTTP 403 response for failed Twilio signature checks."""
    return Response(content="Forbidden", status_code=403)


async def _read_form(request: Request) -> dict[str, str]:
    """Parse urlencoded Twilio bodies without python-multipart."""
    raw = (await request.body()).decode()
    return {k: v for k, v in parse_qsl(raw, keep_blank_values=True)}


def _token() -> str | None:
    if _auth_token is not None:
        return _auth_token
    if _telephony is not None:
        return _telephony.validator
    return None


@router.post("/twilio/voice")
async def twilio_voice(request: Request) -> Response:
    form = await _read_form(request)
    ok = signature_ok(
        twilio_validation_url(request),
        form,
        request.headers.get("X-Twilio-Signature", ""),
        _token(),
    )
    if not ok:
        return reject_bad_signature()
    for key, value in request.query_params.items():
        form.setdefault(key, value)
    if _telephony is None:
        return Response(content="Telephony not configured", status_code=503)
    try:
        return _telephony.handle_voice(form, True)
    except BadSignature:
        return reject_bad_signature()


@router.post("/twilio/status")
async def twilio_status(request: Request) -> Response:
    form = await _read_form(request)
    ok = signature_ok(
        twilio_validation_url(request),
        form,
        request.headers.get("X-Twilio-Signature", ""),
        _token(),
    )
    if not ok:
        return reject_bad_signature()
    for key, value in request.query_params.items():
        form.setdefault(key, value)
    if _telephony is None:
        return Response(content="Telephony not configured", status_code=503)
    try:
        _telephony.handle_status(form, True)
    except BadSignature:
        return reject_bad_signature()
    return Response(status_code=204)


@router.post("/twilio/sms")
async def twilio_sms(request: Request) -> Response:
    form = await _read_form(request)
    ok = signature_ok(
        twilio_validation_url(request),
        form,
        request.headers.get("X-Twilio-Signature", ""),
        _token(),
    )
    if not ok:
        return reject_bad_signature()
    if _telephony is None:
        return Response(content="Telephony not configured", status_code=503)
    try:
        reply = _telephony.handle_sms(form, True)
    except BadSignature:
        return reject_bad_signature()
    if reply:
        body = f"<Response><Message>{escape(reply)}</Message></Response>"
    else:
        body = "<Response></Response>"
    return Response(content=body, media_type="application/xml")
