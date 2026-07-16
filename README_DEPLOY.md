# okx-damp-validator — 部署清單

系統全自動：每日 UTC 08–09 鎖定明日到期 pin verdict（T≈24h，預註冊）、
回填交割價、累積 Stage-1 SPRT / Stage-2 bootstrap / damp 估計。
runner 延遲 1–4h 免疫（結算回填任意小時可跑；verdict 遲到記 MISSED_WINDOW 不補做）。

## 你必須做的事（僅此 5 項，其餘零人工）

1. **建 demo key**：OKX → Trade → Demo Trading → Personal Center →
   Demo Trading API → Create（勾 Read + Trade）。
2. **切帳戶模式**：demo 個人中心 → Multi-currency margin（僅 Track B 下單需要；
   Track A 純測量可跳過，但建議先切好）。
3. **填 Secrets**：repo → Settings → Secrets and variables → Actions →
   New repository secret × 3：`OKX_DEMO_KEY` / `OKX_DEMO_SECRET` / `OKX_DEMO_PASS`。
4. **填 USER_FILL ①**：`config.py` 的 `DEALER_SIGN_MODEL`（你的 UFT dealer 符號慣例）。
   （可選 USER_FILL ②：`PIN_FIRE_K`，預設 0.5。）
5. **啟動**：push 到 GitHub → Actions 頁 → okx-damp-validator → Run workflow
   （首次手動跑一次驗證連通，之後 cron 自動）。

## 凍結契約

`config.py` 凍結區（BAND_SIGMA=0.674 等）在第一個 verdict 落地後永不修改。
修改 = 已累積樣本全部作廢，計數歸零。

## 讀結果

每次 run 的日誌尾部 `[REPORT]` JSON：
- `stage1_SPRT.state`：`CONTINUE` / `ACCEPT_H1_EDGE`（磁鐵是真的）/ `ACCEPT_H0_LUCK`（塑膠，關閉 L1）
- `stage2_bootstrap.verdict`：`STAGE2_PASS` 後才允許 $1,000 真錢 1x；平穩 3 個月後 2x；3x 永久上限
- `damp_hat`：<1 = pin 有阻尼；≈1 = 無效果。回填模擬器即得更新後的報酬分布

## Track B（可選）

`config.py` 設 `ENABLE_DEMO_ORDERS = True` → PIN 日自動用假錢賣 1 口跨式，
僅用於實測價差/成交率回填成本參數；其數據不進 SPRT。
