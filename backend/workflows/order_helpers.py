"""Order projection helpers for workflow nodes."""


def project_tp_from_rr(action: str, entry_price: float, sl_price: float, target_rr: float) -> float:
    if entry_price <= 0 or sl_price <= 0 or target_rr <= 0:
        return 0.0
    risk = abs(entry_price - sl_price)
    if risk <= 0:
        return 0.0
    action = action.upper()
    if action == "BUY":
        return entry_price + (risk * target_rr)
    if action == "SELL":
        return entry_price - (risk * target_rr)
    return 0.0
