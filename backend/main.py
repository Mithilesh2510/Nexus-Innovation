"""
Healthcare Supply Chain Intelligence -- FastAPI backend.

Features:
- Probabilistic demand forecasting with bootstrapped residual bands (p50/p90/p95).
- Fast vectorized Monte Carlo stockout simulation.
- Control-chart anomaly detection with lagged baseline EWMA + CUSUM.
- Real-time inter-facility transfer opportunities & one-click dispatching.
- Budget-constrained procurement recommendation & purchase order generation.
- Supplier intelligence matrix with historical delay & reliability analysis.
- Macro network stress-tester for systemic health shocks.
- Comprehensive audit & compliance summary.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_loader import STORE
from state import get_all_risk, risk_to_dict, _cache, CACHE_TTL_SECONDS
from routers import (
    auth as auth_router,
    dashboard,
    inventory,
    anomalies,
    procurement,
    transfers,
    suppliers,
    simulations,
    audit,
)

app = FastAPI(
    title="Healthcare Supply Chain Intelligence API",
    version="2.0",
    description="Enterprise API for hospital network inventory, forecasting, risk modeling, and procurement optimization."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount modular routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(inventory.router)
app.include_router(anomalies.router)
app.include_router(procurement.router)
app.include_router(transfers.router)
app.include_router(suppliers.router)
app.include_router(simulations.router)
app.include_router(audit.router)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "healthcare-supply-chain-intelligence",
        "version": "2.0-optimized",
    }
