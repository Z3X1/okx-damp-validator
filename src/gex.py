"""L3 SIGNALS — GEX per strike，dealer 符號外部化到 config（USER_FILL ①）
v1.1: markVol 健全性檢查 + 實現波動 fallback（demo 環境 opt-summary 髒數據防禦）"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEALER_SIGN_MODEL

def dealer_sign(instId: str) -> float:
    if DEALER_SIGN_MODEL == "call_pos_put_neg":
        return +1.0 if instId.endswith("-C") else -1.0
    if DEALER_SIGN_MODEL == "all_pos":
        return +1.0
    raise ValueError(f"未知 DEALER_SIGN_MODEL: {DEALER_SIGN_MODEL}")

def nearest_daily_expiry(instruments, now_utc):
    from datetime import timedelta
    target = (now_utc + timedelta(days=1)).strftime("%y%m%d")
    codes = {i["instId"].split("-")[2] for i in instruments if i["state"] == "live"}
    if target in codes:
        return target
    future = sorted(c for c in codes if c > now_utc.strftime("%y%m%d"))
    return future[0] if future else None

def realized_sigma_24h(cli, spot):
    """fallback：24 根 1H K 線的實現波動 → σ24h（美元）。真實行情，與期權標記獨立。"""
    rows = cli.candles("BTC-USDT", "1H", 169)
    closes = [float(r[4]) for r in rows][::-1]          # OKX 回傳新到舊，反轉
    if len(closes) < 100:
        return None
    lr = [math.log(closes[i+1]/closes[i]) for i in range(len(closes)-1)]
    m = sum(lr)/len(lr)
    var = sum((x-m)**2 for x in lr)/(len(lr)-1)
    return (var**0.5) * (24**0.5) * spot

def pin_and_sigma(cli, fam, expiry_code):
    """回傳 (pin, sigma_24h_usd, iv_used)。IV 健全區間 [5%, 500%]，壞值走實現波動。"""
    S = cli.spot()
    oi = {d["instId"]: float(d["oi"]) for d in cli.open_interest(fam)}
    gex, ivs = {}, []
    for g in cli.opt_summary(fam):
        iid = g["instId"]; parts = iid.split("-")
        if parts[2] != expiry_code or iid not in oi:
            continue
        k = float(parts[3])
        gamma = float(g.get("gamma") or 0)
        gex[k] = gex.get(k, 0.0) + dealer_sign(iid) * abs(gamma) * oi[iid]
        mv = float(g.get("markVol") or 0)
        if 0.05 < mv < 5.0:                              # 健全性閘門
            ivs.append((abs(k - S), mv))
    if not gex:
        return None, None, None
    pin = max(gex, key=lambda k: abs(gex[k]))
    if ivs:                                              # 取最接近 ATM 的健全 IV
        ivs.sort()
        iv = ivs[0][1]
        sigma = iv * (1/365)**0.5 * S
        return pin, sigma, iv
    sigma = realized_sigma_24h(cli, S)                   # fallback：實現波動
    if sigma is None:
        return None, None, None
    iv_equiv = sigma / S * 365**0.5
    return pin, sigma, iv_equiv
