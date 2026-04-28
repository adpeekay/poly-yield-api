import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, Request
from collections import defaultdict
from functools import lru_cache
from pydantic import BaseModel
from model import annual_yield

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# --- Rate limiting configuration ---
RATE_LIMIT = 10        # max requests
RATE_WINDOW = 60       # seconds

_request_log = defaultdict(list)

def check_rate_limit(request: Request):
    ip = request.client.host
    now = time.time()

    # Drop old timestamps
    _request_log[ip] = [
        t for t in _request_log[ip]
        if now - t < RATE_WINDOW
    ]

    if len(_request_log[ip]) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again."
        )

    _request_log[ip].append(now)

# --- Simple timed cache ---
_CACHE_TTL = 6 * 60 * 60  # 6 hours
_cached_at = {}


@lru_cache(maxsize=1024)
def cached_annual_yield(
    lat,
    lon,
    timezone,
    no_panels,
    slope_ns,
    max_cell_tilt,
    temp_air,
    wind_speed,
    year,
):
    return annual_yield(
        lat=lat,
        lon=lon,
        timezone=timezone,
        no_panels=no_panels,
        slope_ns=slope_ns,
        max_cell_tilt=max_cell_tilt,
        temp_air=temp_air,
        wind_speed=wind_speed,
        year=year,
    )

def get_cached_result(*args):
    now = time.time()
    cache_hit = False

    if args in _cached_at and now - _cached_at[args] < _CACHE_TTL:
        cache_hit = True
    else:
        _cached_at[args] = now

    result = cached_annual_yield(*args)
    return result, cache_hit

app = FastAPI(title="PV Yield API")

# CORS – allow your Siteglide domain (we'll tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.polysolar.co.uk"],  # temporary – OK for testing
    allow_methods=["POST"],
    allow_headers=["*"],
)

class YieldRequest(BaseModel):
    lat: float
    lon: float
    timezone: str = "UTC"
    slope_ns: float = 2.0
    max_cell_tilt: int = 60
    temp_air: float = 20.0
    wind_speed: float = 3.0
    year: int = 2024


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/calculate")
def calculate(req: YieldRequest, request: Request):

    check_rate_limit(request)

    start = time.time()

    (annual_kwh, kwh_per_kwp, _), cache_hit = get_cached_result(
        round(req.lat, 3),        # round for privacy + cache efficiency
        round(req.lon, 3),
        req.timezone,
        getattr(req, "no_panels", 1),
        req.slope_ns,
        req.max_cell_tilt,
        req.temp_air,
        req.wind_speed,
        req.year,
    )

    elapsed = time.time() - start

    logging.info(
        "calc completed | lat=%.3f lon=%.3f panels=%d cache=%s time=%.2fs",
        req.lat,
        req.lon,
        getattr(req, "no_panels", 1),
        "HIT" if cache_hit else "MISS",
        elapsed,
    )

    return {
        "annual_kwh": round(annual_kwh, 1),
        "kwh_per_kwp": round(kwh_per_kwp, 0),
    }
