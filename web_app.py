#!/usr/bin/env python3
"""SortSmart — AI waste-sorting assistant for India.
Supports Ollama (local), Groq, and Anthropic Claude as AI providers.
Includes HTTP Basic Auth (set APP_PASSWORD env var to protect the app).
"""

import argparse
import base64
import functools
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

# Load .env FIRST so provider/key env vars are available before anything else
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name(".env"), override=True)

try:
    from flask import Flask, jsonify, render_template, request, send_from_directory, Response
    from werkzeug.exceptions import RequestEntityTooLarge
except ImportError as exc:
    raise SystemExit(
        "Web dependencies are missing. Run: python -m pip install -r requirements.txt"
    ) from exc

# ---------------------------------------------------------------------------
# Provider selection — now dotenv is already loaded so env vars are correct
#
# Smart dual-provider mode:
#   SORTSMART_PROVIDER=ollama  → Ollama/LLaVA for PHOTO, Groq for DESCRIPTION
#   This gives best of both: free local vision + multilingual text (Hindi/Punjabi)
# ---------------------------------------------------------------------------
_provider_env = os.environ.get("SORTSMART_PROVIDER", "").strip().lower()

if _provider_env == "ollama":
    from sortsmart_ollama import analyze, active_provider_name  # type: ignore
    # Use Groq for description/text mode — LLaVA ignores language instructions
    _groq_key = os.environ.get("GROQ_API_KEY", "")
    if _groq_key and not _groq_key.startswith("your_"):
        from sortsmart import analyze_description  # type: ignore[assignment]
        _TEXT_PROVIDER = "groq"
    else:
        from sortsmart_ollama import analyze_description  # type: ignore[assignment]
        _TEXT_PROVIDER = "ollama"
    VISION_SUPPORTED = True
elif _provider_env == "anthropic" or (_provider_env != "groq" and os.environ.get("ANTHROPIC_API_KEY")):
    from sortsmart_claude import analyze, analyze_description, active_provider_name  # type: ignore
    _TEXT_PROVIDER = "anthropic"
    VISION_SUPPORTED = True
else:
    from sortsmart import analyze, analyze_description  # type: ignore[assignment]
    def active_provider_name():  # type: ignore[misc]
        return "Groq (text-only)"
    _TEXT_PROVIDER = "groq"
    VISION_SUPPORTED = False


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 128 * 1024
MAX_DESCRIPTION_LENGTH = 300
ALLOWED_MEDIA_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
SUPPORTED_LANGUAGES = {"English", "Hindi", "Punjabi"}
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

# ---------------------------------------------------------------------------
# Security — HTTP Basic Auth + Rate Limiting + Security Headers
# ---------------------------------------------------------------------------
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
_APP_USERNAME = os.environ.get("APP_USERNAME", "sortsmart").strip()

# Simple in-memory rate limiter: max 30 requests/min per IP
_rate_store: dict = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = 60  # seconds


def _check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    timestamps = _rate_store[ip]
    # Remove old entries outside the window
    _rate_store[ip] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True


def _check_auth(req) -> bool:
    """Return True if auth passes (or no password is set)."""
    if not _APP_PASSWORD:
        return True  # No password set → open access (local mode)
    auth = req.authorization
    if not auth:
        return False
    # Constant-time comparison to prevent timing attacks
    user_ok = hashlib.sha256(auth.username.encode()).digest() == \
              hashlib.sha256(_APP_USERNAME.encode()).digest()
    pass_ok = hashlib.sha256(auth.password.encode()).digest() == \
              hashlib.sha256(_APP_PASSWORD.encode()).digest()
    return user_ok and pass_ok


def _auth_required(response: Response) -> Response:
    """Return a 401 response asking for credentials."""
    return Response(
        "🔒 SortSmart is password-protected.\n"
        "Enter the username and password to continue.",
        401,
        {"WWW-Authenticate": 'Basic realm="SortSmart"'},
    )


def require_auth(f):
    """Decorator: require HTTP Basic Auth if APP_PASSWORD is set."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _check_auth(request):
            return _auth_required(Response())
        return f(*args, **kwargs)
    return decorated


@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self), camera=(self)"
    # Strict CSP — allow self + CDN for Leaflet map
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self' https://unpkg.com 'unsafe-inline'; "
        "img-src 'self' data: https://*.tile.openstreetmap.org; "
        "connect-src 'self' https://nominatim.openstreetmap.org https://overpass-api.de "
        "https://overpass.kumi.systems https://maps.mail.ru;"
    )
    return response


@app.get("/api/status")
def api_status():
    """Return the active AI provider name. Useful for health checks (no auth)."""
    return jsonify(provider=active_provider_name(), vision=VISION_SUPPORTED)


@app.get("/api/ollama-status")
@require_auth
def ollama_status_endpoint():
    """Return Ollama health, available models, and vision model info."""
    try:
        from sortsmart_ollama import ollama_status
        return jsonify(ollama_status())
    except Exception as exc:
        return jsonify(error=str(exc)), 500


@app.get("/")
@require_auth
def index():
    return render_template("index.html")


@app.get("/service-worker.js")
def service_worker():
    return send_from_directory(app.static_folder, "service-worker.js")


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify(error="Choose an image smaller than 5 MB."), 413


@app.post("/api/analyze")
@require_auth
def analyze_image():
    # Rate limiting
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if not _check_rate_limit(client_ip):
        return jsonify(error="Too many requests. Please wait a moment and try again."), 429

    image = request.files.get("image")
    if image is not None and not image.filename:
        image = None
    description = request.form.get("description", "").strip()
    if bool(image) == bool(description):
        return jsonify(error="Choose a photo or enter a description, not both."), 400

    language = request.form.get("language", "English").strip()
    if language not in SUPPORTED_LANGUAGES:
        return jsonify(error="Choose English, Hindi, or Punjabi."), 400

    if image is not None:
        media_type = (image.mimetype or "").lower()
        if media_type not in ALLOWED_MEDIA_TYPES:
            return jsonify(error="Use a JPEG, PNG, GIF, or WebP image."), 415

        # Block photo uploads when vision is not supported by the active provider
        if not VISION_SUPPORTED:
            return jsonify(error=(
                "📷 Photo mode is not supported by the current provider (Groq is text-only). "
                "Set SORTSMART_PROVIDER=ollama or add ANTHROPIC_API_KEY to enable photo mode."
            )), 400

        image_bytes = image.read()
        if not image_bytes:
            return jsonify(error="The selected image is empty."), 400
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            return jsonify(error="Choose an image smaller than 5 MB."), 413
        analyze_request = lambda: analyze(image_bytes, media_type, lang=language)
    else:
        if len(description) > MAX_DESCRIPTION_LENGTH:
            return jsonify(error="Description must be 300 characters or fewer."), 400
        analyze_request = lambda: analyze_description(description, lang=language)

    try:
        result = analyze_request()
    except (RuntimeError, ValueError) as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(result)


def _distance_km(lat1, lon1, lat2, lon2):
    radius_km = 6371
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(lon2 - lon1)
    distance = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(min(1, math.sqrt(distance)))


@app.get("/api/dropoffs")
@require_auth
def nearby_dropoffs():
    try:
        latitude = float(request.args["lat"])
        longitude = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify(error="A valid latitude and longitude are required."), 400
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return jsonify(error="A valid latitude and longitude are required."), 400

    query = (
        "[out:json][timeout:12];"
        f"(node(around:5000,{latitude},{longitude})[amenity=recycling];"
        f"way(around:5000,{latitude},{longitude})[amenity=recycling];"
        f"relation(around:5000,{latitude},{longitude})[amenity=recycling];);"
        "out center tags;"
    )
    post_data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "SortSmart/1.0 (nearby recycling lookup)",
    }

    data = None
    for mirror in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(
                mirror, data=post_data, headers=post_headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=14) as response:
                data = json.loads(response.read())
            if isinstance(data, dict) and isinstance(data.get("elements"), list):
                break  # success
            data = None
        except Exception:
            data = None
            continue

    # If all mirrors failed, return soft fallback: empty list + google maps link
    if data is None:
        gmaps = f"https://www.google.com/maps/search/recycling+near/@{latitude},{longitude},14z"
        return jsonify(
            places=[],
            radius_km=5,
            fallback=True,
            gmaps_url=gmaps,
            message=(
                "OpenStreetMap recycling data is currently unavailable. "
                "Try searching Google Maps for recycling points near you."
            ),
        )

    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        return jsonify(places=[], radius_km=5, fallback=True,
                       message="Recycling data returned an unexpected response.")

    places = _format_dropoffs(data["elements"], latitude, longitude)
    places.sort(key=lambda place: place["distance_km"])
    return jsonify(places=places[:10], radius_km=5, fallback=False)


def _format_dropoffs(elements, latitude, longitude):
    places = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}
        point = element.get("center", element)
        if not isinstance(point, dict):
            continue
        try:
            place_lat = float(point["lat"])
            place_lon = float(point["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not math.isfinite(place_lat)
            or not math.isfinite(place_lon)
            or not -90 <= place_lat <= 90
            or not -180 <= place_lon <= 180
        ):
            continue
        places.append(
            {
                "name": tags.get("name") or "Recycling point",
                "latitude": place_lat,
                "longitude": place_lon,
                "distance_km": round(
                    _distance_km(latitude, longitude, place_lat, place_lon), 2
                ),
                "details": tags.get("recycling_type") or tags.get("recycling") or "",
                "osm_url": (
                    "https://www.openstreetmap.org/"
                    f"?mlat={place_lat}&mlon={place_lon}#map=17/{place_lat}/{place_lon}"
                ),
            }
        )
    return places


@app.get("/api/geocode")
@require_auth
def geocode_area():
    query = request.args.get("q", "").strip()
    if not query or len(query) > 120:
        return jsonify(error="Enter an area name of 1 to 120 characters."), 400

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1}
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SortSmart/1.0 (area lookup)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            results = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return jsonify(error="Area search is unavailable right now. Try again later."), 502

    if not isinstance(results, list):
        return jsonify(error="Area search returned an invalid response."), 502
    if not results:
        return jsonify(error="That area could not be found. Try a nearby city or postal code."), 404
    try:
        latitude = float(results[0]["lat"])
        longitude = float(results[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Area search returned an invalid location."), 502
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return jsonify(error="Area search returned an invalid location."), 502
    return jsonify(latitude=latitude, longitude=longitude)


def main():
    parser = argparse.ArgumentParser(description="Run the SortSmart phone web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
