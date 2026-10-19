"""Bound candidate bodies before multipart parsing and prevent caching private responses."""

from starlette.responses import JSONResponse

from .config import settings


class CandidateRequestLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/candidate/"):
            await self.app(scope, receive, send)
            return

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        if scope["method"] == "POST":
            limit = (
                settings.candidate_max_audio_bytes + 65536
                if scope["path"].endswith("/audio")
                else 256 * 1024
            )
            # Enforce actual streamed size even without Content-Length. A bounded buffer
            # keeps the multipart parser from spooling an unbounded upload first.
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data = message.get("body", b"")
                size += len(data)
                if size > limit:
                    await JSONResponse(
                        {"detail": "Request exceeds the upload limit"}, status_code=413
                    )(scope, receive, private_send)
                    return
                chunks.append(data)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            await self.app(scope, bounded_receive, private_send)
        else:
            await self.app(scope, receive, private_send)
