"""Operator-side FastAPI server for the AGCS Ground Station."""

import argparse
import os
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
ALLOWED_REMOTE_ROUTES = {
    "checkDH",
    "cleanTimeStr",
    "getDistance",
    "missionState",
    "originPos",
    "setDH",
    "setDepart",
    "setLand",
    "setThreshold",
    "systemData",
    "systemPos",
    "uavHeight",
    "uavLatestPhoto",
    "uavOrientation",
    "uavPos",
    "ugvHeight",
    "ugvLatestPhoto",
    "ugvOrientation",
    "ugvPos",
}


def normalize_remote_url(value):
    value = str(value).strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("remote URL must start with http:// or https://")
    return value


def create_app(remote_url):
    remote_url = normalize_remote_url(remote_url)
    app = FastAPI(title="AGCS Ground Station")
    upstream_session = requests.Session()
    upstream_session.trust_env = False

    @app.get("/api/{route}")
    async def proxy_remote_get(route: str, request: Request):
        if route not in ALLOWED_REMOTE_ROUTES:
            raise HTTPException(status_code=404, detail="Unknown API route")
        try:
            upstream = upstream_session.get(
                f"{remote_url}/{route}",
                params=list(request.query_params.multi_items()),
                timeout=5.0,
            )
        except requests.RequestException as error:
            raise HTTPException(
                status_code=502,
                detail="Remote communication service unavailable",
            ) from error
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get(
                "content-type",
                "application/octet-stream",
            ),
        )

    app.mount(
        "/",
        StaticFiles(directory=str(ROOT), html=True),
        name="ground-station",
    )
    return app


app = create_app(
    os.environ.get("AGCS_REMOTE_URL", "http://127.0.0.1:26969")
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the AGCS Ground Station")
    parser.add_argument(
        "--remote-url",
        default=os.environ.get(
            "AGCS_REMOTE_URL",
            "http://127.0.0.1:26969",
        ),
        help="remote communication API base URL",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    uvicorn.run(
        create_app(args.remote_url),
        host=args.host,
        port=args.port,
    )
