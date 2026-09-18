from typing import Optional, List
from pydantic import BaseModel


class MedicineRiskOut(BaseModel):
    medicine_id: str
    branch_id: str
    name: str
    category: str
    criticality: str
    current_stock: float
    emergency_reserve: float
    forecast_daily_mean: float
    trend_direction: str
    trend_pct_30d: float
    days_of_cover_p50: float
    stockout_probability_pct: float
    expiry_waste_units: float
    expiry_waste_risk_score: float
    overdue_orders_units: int
    supplier_reliability: float
    supplier_lead_time_mean: float
    supplier_lead_time_std: float
    composite_risk_score: float
    risk_tier: str


class SimulateRequest(BaseModel):
    medicine_id: str
    branch_id: str
    demand_multiplier: float = 1.0
    lead_time_extra_days: float = 0.0


class NetworkSimulateRequest(BaseModel):
    scenario_name: str
    demand_multiplier: float = 1.0
    lead_time_extra_days: float = 0.0
    affected_categories: Optional[List[str]] = None
    affected_branches: Optional[List[str]] = None


class DispatchTransferRequest(BaseModel):
    medicine_id: str
    from_branch: str
    to_branch: str
    units: int


class CreateOrderRequest(BaseModel):
    medicine_id: str
    branch_id: str
    units: int
    unit_cost: float


class ExplainRequest(BaseModel):
    medicine_id: str
    branch_id: str
    api_key: Optional[str] = None


class VisionAnalyzeRequest(BaseModel):
    prompt: str = "What is in this image?"
    image_url: str = "https://assets.ngc.nvidia.com/products/api-catalog/phi-3-5-vision/example1b.jpg"
    model: str = "moonshotai/kimi-k3"
    max_tokens: int = 16384
    temperature: float = 1.0
    stream: bool = False
    reasoning_effort: str = "max"

