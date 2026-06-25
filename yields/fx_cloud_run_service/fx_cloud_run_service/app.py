from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
from yahooquery import Ticker
import pandas as pd

app = Flask(__name__)
CORS(app)

PAIRS = {
    "EURUSD": {"label": "EUR/USD", "ticker": "EURUSD=X"},
    "USDJPY": {"label": "USD/JPY", "ticker": "JPY=X"},
    "GBPUSD": {"label": "GBP/USD", "ticker": "GBPUSD=X"},
    "USDCHF": {"label": "USD/CHF", "ticker": "CHF=X"},
    "USDCAD": {"label": "USD/CAD", "ticker": "CAD=X"},
}

VALID_PERIODS = {"1y", "3y", "5y", "10y", "max"}

@app.get("/")
def home():
    return jsonify({"ok": True, "endpoint": "/fx_history?period=10y"})

@app.get("/fx_history")
def fx_history():
    period = request.args.get("period", "10y").lower()
    if period not in VALID_PERIODS:
        period = "10y"

    series = []
    errors = []

    for key, meta in PAIRS.items():
        try:
            df = Ticker(meta["ticker"]).history(period=period, interval="1d")
            if df is None or len(df) == 0:
                errors.append({"pair": key, "error": "No Yahoo data returned"})
                continue

            df = df.reset_index()
            if "date" not in df.columns or "close" not in df.columns:
                errors.append({"pair": key, "error": "Unexpected Yahoo data format"})
                continue

            df = df[["date", "close"]].dropna()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["close"] = df["close"].astype(float)

            series.append({
                "pair": key,
                "label": meta["label"],
                "ticker": meta["ticker"],
                "dates": df["date"].tolist(),
                "rates": df["close"].round(6).tolist(),
            })
        except Exception as exc:
            errors.append({"pair": key, "error": str(exc)})

    status = 200 if series else 502
    return jsonify({
        "source": "Yahoo Finance via yahooquery",
        "period": period,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "series": series,
        "errors": errors,
    }), status

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
