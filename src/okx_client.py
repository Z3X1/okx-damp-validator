"""L2 DATA — OKX v5 client（demo header 常駐；私有端點僅 Track B 使用）"""
import os, hmac, base64, hashlib, json
from datetime import datetime, timezone
from urllib.parse import urlencode
import requests

BASE = "https://www.okx.com"

class OKX:
    def __init__(self):
        self.s = requests.Session()
        self.key    = os.environ.get("OKX_DEMO_KEY", "")
        self.secret = os.environ.get("OKX_DEMO_SECRET", "").encode()
        self.pw     = os.environ.get("OKX_DEMO_PASS", "")

    def _req(self, method, path, params=None, body=None, private=False, retries=3):
        qs = "?" + urlencode(params) if params else ""
        body_s = json.dumps(body) if body else ""
        headers = {"Content-Type": "application/json", "x-simulated-trading": "1"}
        if private:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            sig = base64.b64encode(hmac.new(
                self.secret, f"{ts}{method}{path}{qs}{body_s}".encode(), hashlib.sha256
            ).digest()).decode()
            headers |= {"OK-ACCESS-KEY": self.key, "OK-ACCESS-SIGN": sig,
                        "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.pw}
        last = None
        for i in range(retries):
            try:
                r = self.s.request(method, BASE + path + qs,
                                   data=body_s or None, headers=headers, timeout=15)
                j = r.json()
                if j.get("code") == "0":
                    return j["data"]
                last = RuntimeError(f"OKX {j.get('code')}: {j.get('msg')} @ {path}")
            except Exception as e:
                last = e
            import time as _t; _t.sleep(1.5 * (i + 1))   # 0.8s+ 間隔紀律
        raise last

    # ---- public（Track A 全部只用這些）----
    def spot(self):
        return float(self._req("GET", "/api/v5/market/ticker",
                               {"instId": "BTC-USDT"})[0]["last"])

    def instruments(self, fam):
        return self._req("GET", "/api/v5/public/instruments",
                         {"instType": "OPTION", "instFamily": fam})

    def opt_summary(self, fam, exp=None):
        p = {"instFamily": fam}
        if exp: p["expTime"] = exp                      # yymmdd 過濾
        return self._req("GET", "/api/v5/public/opt-summary", p)

    def open_interest(self, fam):
        return self._req("GET", "/api/v5/public/open-interest",
                         {"instType": "OPTION", "instFamily": fam})

    def delivery_history(self, fam):
        return self._req("GET", "/api/v5/public/delivery-exercise-history",
                         {"instType": "OPTION", "instFamily": fam})

    def server_hour_utc(self):
        ms = int(self._req("GET", "/api/v5/public/time")[0]["ts"])
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    # ---- private（Track B only）----
    def place(self, instId, side, sz):
        return self._req("POST", "/api/v5/trade/order", body={
            "instId": instId, "tdMode": "cross", "side": side,
            "ordType": "market", "sz": str(sz)}, private=True)
