"""Expose Flask's signed session cookie to JSON/mobile clients (same value as Set-Cookie)."""


def signed_session_cookie_pair():
    """
    Return 'session=<signed>' for the current request session, matching Set-Cookie's
    first segment. Mobile sends this as Cookie: ... on the next request when the
    browser/http stack does not merge Set-Cookie reliably (e.g. dart http.Client).
    """
    from flask import current_app, has_request_context, session

    if not has_request_context():
        return None
    try:
        from werkzeug.wrappers import Response as WzResponse

        dummy = WzResponse()
        current_app.session_interface.save_session(current_app, session, dummy)
    except Exception:
        return None

    headers = dummy.headers
    candidates = []
    getlist = getattr(headers, 'getlist', None)
    if callable(getlist):
        try:
            candidates = list(getlist('Set-Cookie'))
        except Exception:
            candidates = []
    if not candidates:
        one = headers.get('Set-Cookie')
        if one:
            candidates = [one]
    for raw in candidates:
        first = raw.split(';', 1)[0].strip()
        if first.lower().startswith('session='):
            return first
    return None
