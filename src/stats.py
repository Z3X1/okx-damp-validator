"""L4 MODEL — Stage-1 SPRT + Stage-2 bootstrap + damp 估計。判準全部來自 config 凍結區。"""
import math, statistics, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SPRT_P0, SPRT_P1, SPRT_ALPHA, SPRT_BETA, STAGE2_MIN_N, STAGE2_PROB_THRESHOLD

def sprt(hits):
    wi = math.log(SPRT_P1 / SPRT_P0)
    li = math.log((1 - SPRT_P1) / (1 - SPRT_P0))
    U = math.log((1 - SPRT_BETA) / SPRT_ALPHA)
    L = math.log(SPRT_BETA / (1 - SPRT_ALPHA))
    llr = 0.0
    for i, h in enumerate(hits, 1):
        llr += wi if h else li
        if llr >= U: return {"state": "ACCEPT_H1_EDGE", "n": i, "llr": round(llr, 3), "U": round(U,3), "L": round(L,3)}
        if llr <= L: return {"state": "ACCEPT_H0_LUCK", "n": i, "llr": round(llr, 3), "U": round(U,3), "L": round(L,3)}
    return {"state": "CONTINUE", "n": len(hits), "llr": round(llr, 3), "U": round(U,3), "L": round(L,3)}

def bootstrap(pnl_prem_units, n_boot=20000, seed=7):
    if len(pnl_prem_units) < 3:
        return {"n": len(pnl_prem_units), "verdict": "INSUFFICIENT"}
    rnd = random.Random(seed)
    n = len(pnl_prem_units)
    means = sorted(
        sum(rnd.choice(pnl_prem_units) for _ in range(n)) / n
        for _ in range(n_boot))
    p_pos = sum(m > 0 for m in means) / n_boot
    passed = (n >= STAGE2_MIN_N) and (p_pos >= STAGE2_PROB_THRESHOLD)
    return {"n": n, "mean": round(statistics.mean(pnl_prem_units), 4),
            "P(mean>0)": round(p_pos, 4),
            "CI90": [round(means[int(0.05*n_boot)], 4), round(means[int(0.95*n_boot)], 4)],
            "verdict": "STAGE2_PASS" if passed else "STAGE2_CONTINUE"}

def damp_hat(verdict_dists, control_moves):
    """damp = 有verdict日 median|settle−pin| ÷ 對照日 median|settle−spot|（σ單位皆可比）"""
    if len(verdict_dists) < 3 or len(control_moves) < 3:
        return None
    num = statistics.median(verdict_dists)
    den = statistics.median(control_moves)
    return round(num / den, 3) if den > 0 else None
