"""
Inter-facility transfer routes and dispatch handling.
"""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query

from data_loader import STORE
from procurement_optimizer import suggest_transfers
from schemas import DispatchTransferRequest
from state import get_all_risk

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


@router.get("")
def transfers(min_stockout_risk_pct: float = Query(40.0)):
    all_risk = get_all_risk()
    suggestions = suggest_transfers(STORE, min_stockout_risk_pct=min_stockout_risk_pct, all_risk=all_risk)
    return [asdict(s) for s in suggestions]


@router.post("/dispatch")
def dispatch_transfer_action(req: DispatchTransferRequest):
    """Execute an inter-facility transfer and rebalance in-memory stock."""
    record = STORE.dispatch_transfer(req.medicine_id, req.from_branch, req.to_branch, req.units)
    if not record:
        raise HTTPException(status_code=400, detail="Unable to dispatch transfer. Check stock availability.")
    get_all_risk(force=True)
    return {
        "status": "success",
        "message": f"Successfully dispatched {record['units']} units of {record['medicine_name']} from {req.from_branch} to {req.to_branch}.",
        "transfer": record,
    }


@router.get("/history")
def transfer_history():
    return STORE.dispatched_transfers
