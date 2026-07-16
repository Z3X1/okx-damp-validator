"""L3 SIGNALS — GEX per strike，dealer 符號外部化到 config（USER_FILL ①）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEALER_SIGN_MODEL

def dealer_sign(instId: str) -> float:
    if DEALER_SIGN_MODEL == "call_pos_put_neg":
        return +1.0 if instId.endswith("-C") else -1.0
    if DEALER_SIGN_MODEL == "all_pos":
        return +1.0
    raise ValueError(f"未知 DEALER_SIGN_MODEL: {DEALER_SIGN_MODEL}")

def nearest_daily_expiry(instruments, now_utc):
    """回傳 T≈24h 的到期碼 yymmdd（明日 08:00 UTC 交割）。動態 key 解析，
    絕不 hardcode 到期日（GEX Pin bug 教訓）。"""
    from datetime import timedelta
    target = (now_utc + timedelta(days=1)).strftime("%y%m%d")
    codes = {i["instId"].split("-")[2] for i in instruments if i["state"] == "live"}
    if target in codes:
        return target
    future = sorted(c for c in codes if c > now_utc.strftime("%y%m%d"))
    return future[0] if future else None

def pin_and_sigma(cli, fam, expiry_code):
    """回傳 (pin_strike, sigma_24h_usd, atm_iv)。σ 由目標到期 ATM markVol 推出。"""
    S = cli.spot()
    oi = {d["instId"]: float(d["oi"]) for d in cli.open_interest(fam)}
    gex, atm_iv, atm_dist = {}, None, 1e18
    for g in cli.opt_summary(fam):
        iid = g["instId"]
        parts = iid.split("-")
        if parts[2] != expiry_code or iid not in oi:
            continue
        k = float(parts[3])
        gamma = float(g.get("gamma") or 0)
        gex[k] = gex.get(k, 0.0) + dealer_sign(iid) * abs(gamma) * oi[iid]
        mv = float(g.get("markVol") or 0)
        if mv > 0 and abs(k - S) < atm_dist:
            atm_dist, atm_iv = abs(k - S), mv
    if not gex or not atm_iv:
        return None, None, None
    pin = max(gex, key=lambda k: abs(gex[k]))
    sigma_usd = atm_iv * (1 / 365) ** 0.5 * S
    return pin, sigma_usd, atm_iv
