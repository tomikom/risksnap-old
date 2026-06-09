"""
Python replacement for the Excel/VBA volatility-surface workflow.

Input:  NVDA_surface.csv, produced by NVDA.py/yahooquery.
Output: S09_FinalSurface.csv, Surface_Table.xlsx, nvda_volatility_surface.png

The script builds a standardized implied-volatility grid by tenor and moneyness,
using the same broad idea as the VBA workbook: clean option-chain IVs, map them
onto standard moneyness buckets, interpolate the core surface, and mark points
that required extrapolation / nearest-neighbour fill.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator


STANDARD_MONEYNESS = np.array([0.40, 0.70, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.30, 1.60])
STANDARD_TENORS = [
    ("1w", 7 / 365.0),
    ("2w", 14 / 365.0),
    ("1m", 30 / 365.0),
    ("2m", 60 / 365.0),
    ("3m", 90 / 365.0),
    ("6m", 180 / 365.0),
    ("1y", 365 / 365.0),
    ("18m", 548 / 365.0),
    ("2y", 730 / 365.0),
    ("3y", 1095 / 365.0),
    ("4y", 1460 / 365.0),
]


def load_and_clean(csv_path: Path, option_type: str = "calls") -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required = {"Tenor", "Moneyness", "impliedVolatility", "optionType"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["optionType"] = df["optionType"].astype(str).str.lower()
    wanted = option_type.lower()
    if wanted in {"call", "calls", "c"}:
        df = df[df["optionType"].str.startswith("call") | (df["optionType"] == "c")]
    elif wanted in {"put", "puts", "p"}:
        df = df[df["optionType"].str.startswith("put") | (df["optionType"] == "p")]

    for col in ["Tenor", "Moneyness", "impliedVolatility"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Tenor", "Moneyness", "impliedVolatility"])
    df = df[(df["Tenor"] > 0) & (df["Moneyness"] > 0) & (df["impliedVolatility"] > 0)]

    # Remove the worst Yahoo chain noise: absurd IVs and extreme strikes distort the surface.
    df = df[(df["impliedVolatility"] <= 5.0) & (df["Moneyness"].between(0.25, 2.00))]

    # Collapse duplicate tenor/moneyness quotes.
    df = (
        df.groupby(["Tenor", "Moneyness"], as_index=False)
        .agg(impliedVolatility=("impliedVolatility", "median"))
        .sort_values(["Tenor", "Moneyness"])
    )
    if len(df) < 3:
        raise ValueError("Not enough cleaned IV points to build a surface.")
    return df


def build_surface(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    points = df[["Tenor", "Moneyness"]].to_numpy(float)
    values = df["impliedVolatility"].to_numpy(float)

    linear = LinearNDInterpolator(points, values, fill_value=np.nan)
    nearest = NearestNDInterpolator(points, values)

    rows = []
    flags = []
    for label, tenor in STANDARD_TENORS:
        row = {"TenorLabel": label, "Tenor": tenor}
        flag_row = {"TenorLabel": label, "Tenor": tenor}
        for money in STANDARD_MONEYNESS:
            val = float(linear(tenor, money))
            flag = 0
            if np.isnan(val):
                val = float(nearest(tenor, money))
                flag = 1  # outside the convex hull: nearest-neighbour extrapolation/fill
            row[f"{money:.2f}"] = val
            flag_row[f"{money:.2f}"] = flag
        rows.append(row)
        flags.append(flag_row)

    surface = pd.DataFrame(rows)
    flag_df = pd.DataFrame(flags)
    return surface, flag_df


def save_outputs(surface: pd.DataFrame, flags: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    final_csv = out_dir / "S09_FinalSurface.csv"
    surface.to_csv(final_csv, index=False)

    xlsx_path = out_dir / "Surface_Table.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        surface.to_excel(writer, sheet_name="Surface", index=False)
        flags.to_excel(writer, sheet_name="ExtrapolationFlags", index=False)
        wb = writer.book
        pct_fmt = wb.add_format({"num_format": "0.00%"})
        tenor_fmt = wb.add_format({"num_format": "0.000"})
        for sheet_name in ["Surface", "ExtrapolationFlags"]:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1, 2)
            ws.set_column(0, 0, 12)
            ws.set_column(1, 1, 10, tenor_fmt)
            ws.set_column(2, 12, 11, pct_fmt if sheet_name == "Surface" else None)

    plot_path = out_dir / "nvda_volatility_surface.png"
    money = STANDARD_MONEYNESS
    tenors = surface["Tenor"].to_numpy(float)
    z = surface[[f"{m:.2f}" for m in money]].to_numpy(float)
    x, y = np.meshgrid(money, tenors)

    fig = plt.figure(figsize=(9, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(x, y, z, linewidth=0, antialiased=True)
    ax.set_title("NVDA Implied Volatility Surface")
    ax.set_xlabel("Moneyness = Strike / Spot")
    ax.set_ylabel("Tenor (years)")
    ax.set_zlabel("Implied Volatility")
    fig.tight_layout()
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)

    print(f"Saved {final_csv}")
    print(f"Saved {xlsx_path}")
    print(f"Saved {plot_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an implied-volatility surface from an option-chain CSV.")
    parser.add_argument("csv", nargs="?", default="NVDA_surface.csv", help="Input surface CSV")
    parser.add_argument("--option-type", default="calls", choices=["calls", "puts"], help="Use calls or puts")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    args = parser.parse_args()

    df = load_and_clean(Path(args.csv), option_type=args.option_type)
    surface, flags = build_surface(df)
    save_outputs(surface, flags, Path(args.out_dir))


if __name__ == "__main__":
    main()
