"""
L6 PRESENT — 儀表板渲染器 + 帳務骨架
每次 workflow 跑完由本檔生成 site/index.html 推上 GitHub Pages。
帳務骨架:fills(逐筆成交)/ equity(每日權益快照)兩表現在建好,
Track B / 實盤開啟後自動進帳,SPRT 測量軌零污染。
"""
import sys, os, json, sqlite3, hashlib, html
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, SPRT_P0, SPRT_P1, BAND_SIGMA, PIN_FIRE_K, STAGE2_MIN_N
from src.stats import sprt, bootstrap, damp_hat

PASSWORD = "Z3X1Damp"          # <<< 改這行換儀表板密碼
SITE_DIR = "site"

ACCT_DDL = """
CREATE TABLE IF NOT EXISTS fills(
  id INTEGER PRIMARY KEY, ts_utc TEXT, day TEXT, instId TEXT, side TEXT,
  sz REAL, px REAL, fee_usd REAL, ordId TEXT, mode TEXT DEFAULT 'demo');
CREATE TABLE IF NOT EXISTS equity(
  day TEXT PRIMARY KEY, ts_utc TEXT, total_eq_usd REAL,
  upl_usd REAL, mode TEXT DEFAULT 'demo');
"""

def ensure_acct(con):
    con.executescript(ACCT_DDL); con.commit()

def snapshot_equity(con):
    """每日一筆權益快照(demo)。失敗靜默——帳務軌故障不得阻塞測量軌。"""
    try:
        from src.okx_client import OKX
        cli = OKX()
        if not cli.key: return
        d = cli._req("GET", "/api/v5/account/balance", private=True)
        eq = float(d[0].get("totalEq") or 0)
        upl = float(d[0].get("upl") or 0) if d[0].get("upl") else 0.0
        now = datetime.now(timezone.utc)
        con.execute("INSERT OR IGNORE INTO equity(day,ts_utc,total_eq_usd,upl_usd) "
                    "VALUES(?,?,?,?)", (now.strftime("%Y-%m-%d"), now.isoformat(), eq, upl))
        con.commit()
    except Exception as e:
        print(f"[EQUITY] skip: {e}")

def gather(con):
    pin = con.execute("SELECT day,spot,pin,sigma_usd,band_usd,settle_px,dist_pin,hit,pnl_prem "
                      "FROM verdicts WHERE verdict='PIN' AND settle_px IS NOT NULL ORDER BY day").fetchall()
    ctl = con.execute("SELECT dist_spot,sigma_usd FROM verdicts "
                      "WHERE verdict='NO_FIRE' AND settle_px IS NOT NULL").fetchall()
    last = con.execute("SELECT day,verdict,spot,pin,sigma_usd,settle_px,dist_pin,hit "
                       "FROM verdicts ORDER BY day DESC LIMIT 30").fetchall()
    n_missed = con.execute("SELECT COUNT(*) FROM verdicts WHERE verdict='MISSED_WINDOW'").fetchone()[0]
    n_pending = con.execute("SELECT COUNT(*) FROM verdicts WHERE settle_px IS NULL "
                            "AND verdict IN ('PIN','NO_FIRE')").fetchone()[0]
    eq = con.execute("SELECT day,total_eq_usd,mode FROM equity ORDER BY day").fetchall()
    n_fills = con.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    return pin, ctl, last, n_missed, n_pending, eq, n_fills

def render(con):
    pin, ctl, last, n_missed, n_pending, eq, n_fills = gather(con)
    hits = [r[7] for r in pin]
    s1 = sprt(hits) if hits else {"state":"WAITING_FIRST_PIN","n":0,"llr":0.0,"U":2.944,"L":-2.944}
    s2 = bootstrap([r[8] for r in pin]) if pin else {"n":0,"verdict":"INSUFFICIENT"}
    dh = damp_hat([r[6]/r[3] for r in pin], [r[0]/r[1] for r in ctl]) if pin and ctl else None
    llr, U, L = s1.get("llr",0.0), s1.get("U",2.944), s1.get("L",-2.944)
    pct = max(0,min(100,(llr-L)/(U-L)*100))
    color = {"ACCEPT_H1_EDGE":"#22c55e","ACCEPT_H0_LUCK":"#ef4444"}.get(s1["state"],"#eab308")
    pw_hash = hashlib.sha256(PASSWORD.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    rows = ""
    for d,v,sp,p,sg,st,dp,h in last:
        if v=="MISSED_WINDOW":
            rows += f"<tr><td>{d}</td><td colspan=6 class=mut>MISSED_WINDOW</td></tr>"; continue
        stl = f"{st:,.0f}" if st else "待交割"
        hh = "" if h is None else ("✅" if h else "❌")
        dpp = f"{dp:,.0f}" if dp is not None else "—"
        rows += (f"<tr><td>{d}</td><td class={'fire' if v=='PIN' else 'mut'}>{v}</td>"
                 f"<td>{sp:,.0f}</td><td>{p:,.0f}</td><td>{sg:,.0f}</td><td>{stl}/{dpp}</td><td>{hh}</td></tr>")

    if eq:
        base = eq[0][1]
        eq_html = f"<div class=grid>" + "".join(
            f"<div class=card><div class=k>{d}</div><div class=v>${e:,.0f}</div>"
            f"<div class=k>{(e/base-1)*100:+.2f}%</div></div>" for d,e,m in eq[-8:]) + "</div>"
    else:
        eq_html = "<p class=mut>尚未開始交易 — Track B 關閉中。fills / equity 表已建好待命,開啟後自動進帳。</p>"

    doc = f"""<!doctype html><html lang=zh-Hant><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex>
<title>damp validator</title><style>
body{{background:#0b0f14;color:#e5e7eb;font:15px/1.6 -apple-system,system-ui;margin:0;padding:16px}}
.wrap{{max-width:640px;margin:auto}}h1{{font-size:19px}}h2{{font-size:15px;color:#9ca3af;margin-top:26px}}
.badge{{display:inline-block;padding:3px 12px;border-radius:99px;background:{color};color:#000;font-weight:700}}
.bar{{position:relative;height:14px;background:#1f2937;border-radius:99px;margin:14px 0 4px}}
.bar i{{position:absolute;top:-3px;left:{pct:.1f}%;width:4px;height:20px;background:#fff;border-radius:2px}}
.bar b{{position:absolute;top:0;height:100%;border-radius:99px;background:{color};width:{pct:.1f}%;opacity:.35}}
.lbl{{display:flex;justify-content:space-between;color:#6b7280;font-size:12px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px}}
.k{{color:#6b7280;font-size:12px}}.v{{font-size:21px;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}td,th{{padding:6px 4px;border-bottom:1px solid #1f2937;text-align:right}}
td:first-child,th:first-child{{text-align:left}}.fire{{color:#f59e0b;font-weight:700}}.mut{{color:#6b7280}}
#gate{{position:fixed;inset:0;background:#0b0f14;display:flex;align-items:center;justify-content:center;z-index:9}}
#gate input{{background:#111827;border:1px solid #374151;color:#fff;padding:10px;border-radius:8px;font-size:16px}}
.ft{{color:#4b5563;font-size:11px;margin-top:28px}}</style></head><body>
<div id=gate><input id=pw type=password placeholder="密碼" onkeydown="if(event.key==='Enter')chk()"></div>
<div class=wrap>
<h1>OKX damp validator <span class=badge>{s1["state"]}</span></h1>
<div class=k>更新 {now.strftime("%Y-%m-%d %H:%M")} UTC(台北 +8)</div>
<h2>Stage-1 SPRT(H₀ p={SPRT_P0} vs H₁ p={SPRT_P1})</h2>
<div class=bar><b></b><i></i></div>
<div class=lbl><span>L={L}(運氣)</span><span>LLR={llr:+.3f}(n={s1["n"]})</span><span>U={U}(edge)</span></div>
<div class=grid>
<div class=card><div class=k>PIN 已交割</div><div class=v>{len(pin)}</div></div>
<div class=card><div class=k>對照組</div><div class=v>{len(ctl)}</div></div>
<div class=card><div class=k>damp_hat</div><div class=v>{dh if dh is not None else "—"}</div></div>
<div class=card><div class=k>缺席 / 待交割</div><div class=v>{n_missed} / {n_pending}</div></div>
</div>
<h2>Stage-2 bootstrap(門檻 n≥{STAGE2_MIN_N} 且 P>0.95)</h2>
<div class=card>{json.dumps(s2, ensure_ascii=False)}</div>
<h2>帳務(mode=demo,fills={n_fills})</h2>{eq_html}
<h2>近 30 筆 verdict</h2>
<table><tr><th>日期</th><th>verdict</th><th>spot</th><th>pin</th><th>σ</th><th>交割/距pin</th><th>hit</th></tr>{rows}</table>
<div class=ft>凍結參數:band={BAND_SIGMA}σ|開火閘={PIN_FIRE_K}σ|一天一筆|MISSED 不補做。
判準凍結於首筆 verdict,永不回改。</div></div>
<script>
async function chk(){{const v=document.getElementById('pw').value;
const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(v));
const h=[...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('');
if(h==='{pw_hash}'){{sessionStorage.g='1';document.getElementById('gate').style.display='none'}}}}
if(sessionStorage.g==='1')document.getElementById('gate').style.display='none';
</script></body></html>"""
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(f"{SITE_DIR}/index.html","w") as f: f.write(doc)
    print(f"[PRESENT] site/index.html 已生成 state={s1['state']} llr={llr:+.3f}")

if __name__ == "__main__":
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("SELECT 1 FROM verdicts LIMIT 1")
    except sqlite3.OperationalError:
        print("[PRESENT] 無 verdicts 表,先建空庫"); 
        from src.pipeline import db as _db; con.close(); con = _db()
    ensure_acct(con)
    snapshot_equity(con)
    render(con)
