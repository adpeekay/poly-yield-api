# -*- coding: utf-8 -*-
"""
Created on Tue Apr 14 10:08:23 2026

@author: Martyn
"""

# model.py
import numpy as np
import pandas as pd
import pvlib


def annual_yield(
    lat,
    lon,
    timezone,
    no_panels=1, #remove this later
    module_azimuth=90,
    max_cell_tilt=60,
    slope_ns=2.0,
    temp_air=12.0,
    wind_speed=3.0,
    year=2024,
):
    """
    Returns:
        annual_kwh (float)
        annual_kwh_per_kwp (float)
        daily_kwh (pd.Series)
    """

    SITE = pvlib.location.Location(lat, lon, timezone)

    # FLEX‑03‑class parameters
    N_CELLS = 110
    CELLS_PER_BYPASS = 2
    N_PAIRS = N_CELLS // CELLS_PER_BYPASS

    P_MPP = 280.0
    V_MPP = 70.8
    I_MPP = 3.96

    V_CELL = V_MPP / N_CELLS
    V_PAIR = V_CELL * CELLS_PER_BYPASS

    # Electrical behaviour
    TEMP_COEFF = -0.0038
    T_REF = 25.0
    IRRAD_THRESHOLD = 10.0
    DECOUPLING_FRACTION = 0.6

    # Time range
    times = pd.date_range(
        start=f"{year}-01-01 00:00",
        end=f"{year}-12-31 23:00",
        freq="1h",
        tz=timezone,
    )

    solpos = SITE.get_solarposition(times)
    clearsky = SITE.get_clearsky(times, model="ineichen")

    # Geometry
    cell_angles = np.linspace(-max_cell_tilt, max_cell_tilt, N_CELLS)

    tilts = []
    azimuths = []
    for ang in cell_angles:
        tilts.append(abs(ang + slope_ns))
        azimuths.append((module_azimuth + (180 if ang < 0 else 0)) % 360)

    # Compute per‑cell currents
    cell_I = np.zeros((N_CELLS, len(times)))

    for i in range(N_CELLS):
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilts[i],
            surface_azimuth=azimuths[i],
            solar_zenith=solpos["zenith"],
            solar_azimuth=solpos["azimuth"],
            dni=clearsky["dni"],
            ghi=clearsky["ghi"],
            dhi=clearsky["dhi"],
        )

        poa_irr = poa["poa_global"].fillna(0)

        temp_cell = pvlib.temperature.faiman(
            poa_global=poa_irr,
            temp_air=temp_air,
            wind_speed=wind_speed,
            u0=25,
            u1=6.84,
        )

        temp_factor = (1 + TEMP_COEFF * (temp_cell - T_REF))
        temp_factor = np.clip(temp_factor, 0, None)

        I = I_MPP * (poa_irr / 1000.0) * temp_factor
        I[poa_irr < IRRAD_THRESHOLD] = 0.0

        cell_I[i, :] = I

    # Series aggregation
    P_series = np.zeros(len(times))

    for t in range(len(times)):
        pair_I = np.zeros(N_PAIRS)
        for p in range(N_PAIRS):
            pair_I[p] = min(cell_I[2*p, t], cell_I[2*p+1, t])

        active = pair_I[pair_I > 0]
        if len(active) == 0:
            continue

        I_ref = np.percentile(active, 75)
        effective = active[active >= DECOUPLING_FRACTION * I_ref]
        if len(effective) == 0:
            continue

        I_string = effective.min()
        V_string = V_PAIR * len(effective)
        P_series[t] = (I_string * V_string) / 1000.0

    series = pd.Series(P_series, index=times)
    daily_kwh = (series.resample("D").sum() * no_panels)
    annual_kwh = daily_kwh.sum()
    annual_kwh_per_kwp = (annual_kwh / no_panels) / (P_MPP / 1000.0)

    return annual_kwh, annual_kwh_per_kwp, daily_kwh