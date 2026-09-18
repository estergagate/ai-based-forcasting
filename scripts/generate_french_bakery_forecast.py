import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

SOURCE_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "french_bakery"
    / "daily_product_sales.csv"
)

MODEL_FILE = (
    BASE_DIR
    / "models"
    / "traditional_baguette_forecast_model.joblib"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "results"
    / "french_bakery"
    / "traditional_baguette_next_day_forecast.json"
)

PRODUCT_NAME = "TRADITIONAL BAGUETTE"


def add_features(daily_sales):
    frame = daily_sales.copy()

    frame["weekday"] = frame.index.dayofweek
    frame["month"] = frame.index.month

    frame["lag_1"] = frame["quantity_sold"].shift(1)
    frame["lag_7"] = frame["quantity_sold"].shift(7)
    frame["lag_14"] = frame["quantity_sold"].shift(14)

    previous_sales = frame["quantity_sold"].shift(1)

    frame["average_7_days"] = (
        previous_sales
        .rolling(7, min_periods=7)
        .mean()
    )

    frame["average_28_days"] = (
        previous_sales
        .rolling(28, min_periods=28)
        .mean()
    )

    return frame


def main():
    if not SOURCE_FILE.exists():
        print("Prepared bakery data was not found.")
        return

    if not MODEL_FILE.exists():
        print("The trained model was not found.")
        print("Run train_french_bakery_model.py first.")
        return

    sales = pd.read_csv(
        SOURCE_FILE,
        parse_dates=["date"],
    )

    product_sales = sales[
        sales["article"] == PRODUCT_NAME
    ].copy()

    product_sales = (
        product_sales
        .groupby("date", as_index=False)
        .agg(
            quantity_sold=("quantity_sold", "sum"),
            typical_price_eur=(
                "average_unit_price_eur",
                "median",
            ),
        )
        .sort_values("date")
    )

    first_date = product_sales["date"].min()
    history_end = product_sales["date"].max()

    full_dates = pd.date_range(
        first_date,
        history_end,
        freq="D",
    )

    daily_sales = (
        product_sales
        .set_index("date")["quantity_sold"]
        .reindex(full_dates, fill_value=0)
        .to_frame()
    )

    daily_sales.index.name = "date"

    forecast_date = history_end + pd.Timedelta(days=1)

    # Add an empty future day. Its features use only earlier sales.
    daily_sales.loc[forecast_date, "quantity_sold"] = np.nan

    feature_frame = add_features(daily_sales)

    saved_model = joblib.load(MODEL_FILE)

    model = saved_model["model"]
    feature_names = saved_model["features"]

    forecast_features = feature_frame.loc[
        [forecast_date],
        feature_names,
    ]

    if forecast_features.isna().any().any():
        print("There is not enough sales history to forecast.")
        return

    predicted_quantity = float(
        model.predict(forecast_features)[0]
    )

    predicted_quantity = max(0, predicted_quantity)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    forecast = {
        "dataset": "French bakery daily sales from Kaggle",
        "product": PRODUCT_NAME,
        "forecast_date": str(forecast_date.date()),
        "history_end": str(history_end.date()),
        "predicted_quantity": round(predicted_quantity, 2),
        "unit": "pieces",
        "training_records": int(len(daily_sales) - 1),
        "typical_price_eur": round(
            float(product_sales["typical_price_eur"].median()),
            2,
        ),
        "actual_quantity": None,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(forecast, file, indent=4)

    print("\nNEXT-DAY FORECAST — FRENCH BAKERY DEMONSTRATION\n")
    print(f"Product: Traditional Baguette")
    print(
        f"History ends: "
        f"{history_end.strftime('%B %d, %Y')}"
    )
    print(
        f"Forecast date: "
        f"{forecast_date.strftime('%B %d, %Y')}"
    )
    print(
        f"Expected sales: "
        f"{predicted_quantity:,.2f} pieces"
    )
    print(f"\nForecast saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()