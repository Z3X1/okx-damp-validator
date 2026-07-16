"""
L7 PIPELINE — 單一進入點，冪等，延遲容忍。
每次執行按序做三件事（各自可獨立跳過）：
  1) SETTLE : 有未結算 verdict 且交割價已公布 → 回填（任何小時可跑，延遲免疫）
  2) VERDICT: UTC 8–9 時且今日尚未鎖定 → 鎖定明日到期 verdict（T≈24h，預註冊）
  3) MISSED : UTC 10–12 時且今日無 verdict → 記 MISSED_WINDOW（反倖存者偏差）
之後輸出 Stage-1 / Stage-2 / damp 報告。
"""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (INST_FAMILY, DB_PATH, PIN_FIRE_K, BAND_SIGMA, COST_PREM,
                    VERDICT_HOURS_UTC, MISSED_HOURS_UTC,
                    ENABLE_DEMO_ORDERS, ORDER_SIZE_CONTRACTS)
from src.okx_client import OKX
from src.gex import nearest_daily_expiry, pin_and_sigma
from src.stats import sprt, bootstrap, damp_hat

DDL = """CREATE TABLE IF NOT EXISTS verdicts(
  id INTEGER PRIMARY KEY, day TEXT UNIQUE, ts_utc TEXT, expiry_code TEXT,
  spot REAL, pin REAL, sigma_usd REAL, atm_iv REAL,
  verdict TEXT,               -- PIN / NO_FIRE / MISSED_WINDOW
  band_usd REAL,              -- 凍結: BAND_SIGMA * sigma_usd（進場時計算並鎖定）
  ord_ids TEXT,
  settle_px REAL, dist_pin REAL, dist_spot REAL, hit INTEGER, pnl_prem REAL,
  locked INTEGER DEFAULT 1)"""

def db():
    c = sqlite3.connect(DB_PATH); c.execute(DDL); c.commit(); return c

def do_settle(cli, con):
    rows = con.execute("SELECT day, expiry_code, spot, pin, sigma_usd, band_usd, verdict "
                       "FROM verdicts WHERE settle_px IS NULL AND verdict != 'MISSED_WINDOW'").fetchall()
    if not rows: return
    # 交割價索引：{yymmdd: px}
    deliv = {}
    for d in cli.delivery_history(INST_FAMILY):
        for det in d.get("details", []):
            code = det.get("insId", det.get("instId", "")).split("-")
            if len(code) >= 3 and det.get("px"):
                deliv[code[2]] = float(det["px"])
    for day, exp, spot, pin, sig, band, v in rows:
        if exp not in deliv: continue
        px = deliv[exp]
        d_pin, d_spot = abs(px - pin), abs(px - spot)
        hit = int(d_pin <= band)
        prem = 0.8 * sig                                  # BS ATM 跨式 ≈ 0.8σ√t
        pnl = (prem - d_pin) / prem - COST_PREM           # premium 單位，預註冊公式
        con.execute("UPDATE verdicts SET settle_px=?,dist_pin=?,dist_spot=?,hit=?,pnl_prem=? "
                    "WHERE day=?", (px, d_pin, d_spot, hit, round(pnl,4), day))
        print(f"[SETTLE] {day} exp={exp} px={px:,.0f} |px−pin|={d_pin:,.0f} "
              f"band={band:,.0f} hit={hit} pnl={pnl:+.3f}prem")
    con.commit()

def do_verdict(cli, con, now):
    today = now.strftime("%Y-%m-%d"); h = now.hour
    if con.execute("SELECT 1 FROM verdicts WHERE day=?", (today,)).fetchone():
        return
    if VERDICT_HOURS_UTC[0] <= h <= VERDICT_HOURS_UTC[1]:
        exp = nearest_daily_expiry(cli.instruments(INST_FAMILY), now)
        if not exp:
            print("[VERDICT] 無可用到期，跳過"); return
        pin, sig, iv = pin_and_sigma(cli, INST_FAMILY, exp)
        if pin is None:
            print("[VERDICT] opt-summary 不足，跳過"); return
        spot = cli.spot()
        fire = abs(spot - pin) <= PIN_FIRE_K * sig
        verdict = "PIN" if fire else "NO_FIRE"
        band = BAND_SIGMA * sig
        ords = ""
        if fire and ENABLE_DEMO_ORDERS:                   # Track B（不進 SPRT）
            k = int(pin)
            ids = []
            for suf in ("C", "P"):
                try:
                    r = cli.place(f"BTC-USD-{exp}-{k}-{suf}", "sell", ORDER_SIZE_CONTRACTS)
                    ids.append(r[0].get("ordId", "?"))
                except Exception as e:
                    ids.append(f"ERR:{e}")
            ords = ",".join(ids)
        con.execute("INSERT INTO verdicts(day,ts_utc,expiry_code,spot,pin,sigma_usd,atm_iv,"
                    "verdict,band_usd,ord_ids) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (today, now.isoformat(), exp, spot, pin, sig, iv, verdict, band, ords))
        con.commit()
        print(f"[VERDICT] {today} LOCKED exp={exp} spot={spot:,.0f} pin={pin:,.0f} "
              f"σ={sig:,.0f} band={band:,.0f} verdict={verdict}")
    elif MISSED_HOURS_UTC[0] <= h <= MISSED_HOURS_UTC[1]:
        con.execute("INSERT INTO verdicts(day,ts_utc,verdict) VALUES(?,?,'MISSED_WINDOW')",
                    (today, now.isoformat()))
        con.commit()
        print(f"[MISSED] {today} runner 延遲落在 {h}:00 UTC，記錄缺席（不補做）")

def report(con):
    pin_rows = con.execute("SELECT hit, pnl_prem, dist_pin, sigma_usd FROM verdicts "
                           "WHERE verdict='PIN' AND settle_px IS NOT NULL ORDER BY day").fetchall()
    ctl_rows = con.execute("SELECT dist_spot, sigma_usd FROM verdicts "
                           "WHERE verdict='NO_FIRE' AND settle_px IS NOT NULL").fetchall()
    n_missed = con.execute("SELECT COUNT(*) FROM verdicts WHERE verdict='MISSED_WINDOW'").fetchone()[0]
    out = {"settled_PIN": len(pin_rows), "settled_control": len(ctl_rows), "missed_days": n_missed}
    if pin_rows:
        out["stage1_SPRT"] = sprt([r[0] for r in pin_rows])
        out["stage2_bootstrap"] = bootstrap([r[1] for r in pin_rows])
        out["damp_hat"] = damp_hat([r[2]/r[3] for r in pin_rows],
                                   [r[0]/r[1] for r in ctl_rows])
    print("[REPORT]", json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    cli = OKX()
    now = cli.server_hour_utc()          # 用交易所時鐘，杜絕 runner 時鐘漂移
    con = db()
    do_settle(cli, con)
    do_verdict(cli, con, now)
    report(con)
