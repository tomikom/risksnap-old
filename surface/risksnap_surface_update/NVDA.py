from yahooquery import Ticker
import pandas as pd

ticker = "NVDA"
t = Ticker(ticker)

# Get option chain
chain = t.option_chain.reset_index()

# Get underlying market price
price_data = t.price[ticker]
underlying_mp = price_data.get("regularMarketPrice")

# Assumption: annual risk-free rate
r = 0.04

# Get dividend yield
summary = t.summary_detail[ticker]
dividend_yield = summary.get("dividendYield", 0) or 0

# Add calculated columns
chain["Underlying MP"] = underlying_mp
chain["Dividend Yield"] = dividend_yield
chain["r"] = r
chain["Moneyness"] = chain["strike"] / underlying_mp
chain["Tenor"] = (
    pd.to_datetime(chain["expiration"]) - pd.Timestamp.today().normalize()
).dt.days / 365.0

# Create surface output
surface = chain[
    [
        "expiration",
        "Tenor",
        "optionType",
        "strike",
        "Moneyness",
        "Underlying MP",
        "Dividend Yield",
        "r",
        "lastPrice",
        "bid",
        "ask",
        "impliedVolatility",
        "openInterest",
        "volume"
    ]
].copy()

surface.to_csv("NVDA_surface.csv", index=False)

print("Ticker:", ticker)
print("Underlying MP:", underlying_mp)
print("Dividend Yield:", dividend_yield)
print("Risk Free Rate:", r)
print("Rows:", len(surface))
print(surface.head(20))
print("Saved NVDA_surface.csv")
