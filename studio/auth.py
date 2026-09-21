"""Application authentication for localhost and managed LAN deployments."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

SESSION_COOKIE_NAME = "shikishi_session"


class ApplicationAuth:
    """Validate bearer tokens and short-lived browser sessions."""

    def __init__(self, token: str | None, session_ttl_seconds: int, enabled: bool) -> None:
        self._token = token
        self._session_ttl_seconds = session_ttl_seconds
        self.enabled = enabled

    def is_public_path(self, path: str) -> bool:
        return path in {
            "/healthz",
            "/readyz",
            "/login",
            "/auth/login",
            "/static",
        } or path.startswith("/static/")

    def is_authenticated(self, request: Request) -> bool:
        if not self.enabled:
            return True
        authorization = request.headers.get("authorization", "")
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and self.verify_token(credentials.strip()):
            return True
        session = request.cookies.get(SESSION_COOKIE_NAME)
        return session is not None and self._verify_session(session)

    def verify_token(self, token: str | None) -> bool:
        if self._token is None or token is None:
            return False
        return hmac.compare_digest(token, self._token)

    def issue_session(self, response: Response) -> None:
        issued_at = str(int(time.time()))
        response.set_cookie(
            SESSION_COOKIE_NAME,
            f"{issued_at}.{self._sign(issued_at)}",
            max_age=self._session_ttl_seconds,
            httponly=True,
            samesite="lax",
            path="/",
        )

    def login_page(self) -> HTMLResponse:
        return HTMLResponse(
            """<!doctype html>
<html lang="ja">
  <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Shikishi Studio login</title></head>
  <body style="font-family: sans-serif; max-width: 32rem; margin: 4rem auto; padding: 0 1rem">
    <h1>Shikishi Studio</h1>
    <p>LANモードです。起動時に設定した認証トークンを入力してください。</p>
    <form action="/auth/login" method="post">
      <label for="token">認証トークン</label><br>
      <input id="token" name="token" type="password" autocomplete="current-password" required
        style="width: 100%; box-sizing: border-box; margin: .5rem 0 1rem; padding: .6rem">
      <button type="submit">ログイン</button>
    </form>
  </body>
</html>""",
            headers={"Cache-Control": "no-store"},
        )

    async def login(self, request: Request) -> Response:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        raw_body = await request.body()
        token: str | None = None
        if content_type == "application/json":
            try:
                payload = json.loads(raw_body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("token"), str):
                token = payload["token"]
        else:
            values = parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True)
            token_values = values.get("token", [])
            if token_values:
                token = token_values[0]

        if self.enabled and not self.verify_token(token):
            if content_type == "application/json":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication token"},
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )
            return HTMLResponse(
                "<p>認証トークンが正しくありません。</p><p><a href='/login'>戻る</a></p>",
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )

        response: Response
        if content_type == "application/json":
            response = JSONResponse({"status": "ok"})
        else:
            response = RedirectResponse("/", status_code=303)
        self.issue_session(response)
        return response

    def unauthorized_response(self, request: Request) -> Response:
        if request.url.path == "/" or "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=307)
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        )

    def _verify_session(self, value: str) -> bool:
        issued_at, separator, signature = value.partition(".")
        if not separator or not issued_at or not signature:
            return False
        try:
            issued = int(issued_at)
        except ValueError:
            return False
        age = int(time.time()) - issued
        if age < 0 or age > self._session_ttl_seconds:
            return False
        return hmac.compare_digest(signature, self._sign(issued_at))

    def _sign(self, value: str) -> str:
        if self._token is None:
            return ""
        return hmac.new(
            self._token.encode("utf-8"), value.encode("ascii"), hashlib.sha256
        ).hexdigest()
