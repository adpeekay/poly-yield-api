from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from model import annual_yield

app = FastAPI(title="PV Yield API")

# CORS – allow your Siteglide domain (we'll tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # temporary – OK for testing
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
def calculate(req: YieldRequest):
    annual_kwh, kwh_per_kwp, _ = annual_yield(
        lat=req.lat,
        lon=req.lon,
        timezone=req.timezone,
        slope_ns=req.slope_ns,
        max_cell_tilt=req.max_cell_tilt,
        temp_air=req.temp_air,
        wind_speed=req.wind_speed,
        year=req.year,
    )

    return {
        "annual_kwh": round(annual_kwh, 1),
        "kwh_per_kwp": round(kwh_per_kwp, 0),
    }