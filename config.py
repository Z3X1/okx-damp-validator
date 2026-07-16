"""
L0 CONFIG — okx-damp-validator
================================================================
凍結區以下的參數 = 預註冊判準。部署後修改任何一項 → 已累積樣本作廢。
"""

# ════════════════════════════════════════════════════════════
# USER_FILL ①：dealer 部位符號模型（你的 UFT 慣例，我無法替你決定）
#   'call_pos_put_neg' : GEX = +call_gamma −put_gamma（最常見慣例）
#   'all_pos'          : GEX = +call_gamma +put_gamma（絕對 gamma 密度）
#   或自訂: 修改 src/gex.py 的 dealer_sign()
# ════════════════════════════════════════════════════════════
DEALER_SIGN_MODEL = "call_pos_put_neg"   # <<< USER_FILL

# ════════════════════════════════════════════════════════════
# USER_FILL ②（可選）：PIN verdict 觸發距離（spot 距 pin 幾個 σ 內才開火）
# 預設 0.5 對應模擬器的 ~35% 開火率假設。部署前可改，部署後凍結。
# ════════════════════════════════════════════════════════════
PIN_FIRE_K = 0.5                          # <<< USER_FILL(optional)

# ════════════════════════════════════════════════════════════
# 凍結區（不是 USER_FILL，永不修改）
# ════════════════════════════════════════════════════════════
BAND_SIGMA   = 0.674   # |settle−pin| ≤ 0.674σ = HIT。0.674 = |N(0,1)| 中位數
                       # → H0(無pin效果) 命中率精確 = 0.5，SPRT 假設成為恆等式
COST_PREM    = 0.052   # OKX 成本佔 premium 比例（費用+價差，Track B 實測後可校準，
                       #  但 Stage-1 判定不依賴此值）
SPRT_P0, SPRT_P1        = 0.50, 0.80
SPRT_ALPHA, SPRT_BETA   = 0.05, 0.05
STAGE2_MIN_N            = 40
STAGE2_PROB_THRESHOLD   = 0.95

# 時窗（UTC）：08:00 交割 → 08–09 時窗鎖明日 verdict（T≈24h）+ 回填昨日結算
VERDICT_HOURS_UTC = (8, 9)     # 含 8、含 9
MISSED_HOURS_UTC  = (10, 12)   # runner 延遲落在此區 → 記 MISSED_WINDOW，不補做
INST_FAMILY = "BTC-USD"
DB_PATH     = "verdicts.sqlite"

# Track B：demo 下單（成本校準用，數據不進 SPRT）。預設關閉。
ENABLE_DEMO_ORDERS = False
ORDER_SIZE_CONTRACTS = 1
