import json
from datetime import datetime, timezone

import joblib
import pandas as pd

from train_forecasting_model import (
    BASE_DIR,
    FEATURES,
    build_features,
    load_data,
    make_model,
)


def main():
    results_dir = BASE_DIR / "data" / "results"
    models_dir = BASE_DIR / "models"

    # Reuse settings selected using 2021 validation data.
    with (
        results_dir / "dairy_product_1_metrics.json"
    ).open(encoding="utf-8") as source:
        evaluation = json.load(source)

    settings = evaluation["chosen_settings"]

    data = load_data()
    last_date = data.index.max()
    forecast_date = last_date + pd.Timedelta(days=1)

    # Require actual observations for the latest historical lags.
    for days in (1, 7, 14, 28):
        reference_date = forecast_date - pd.Timedelta(days=days)

        if (
            reference_date not in data.index
            or pd.isna(data.loc[reference_date, "quantity"])
        ):
            raise ValueError(
                f"Cannot forecast: missing quantity for {reference_date.date()}"
            )

    # Add a blank future date. No future actual value is invented.
    future_row = pd.DataFrame(
        {"quantity": [float("nan")], "status": ["future"]},
        index=pd.DatetimeIndex([forecast_date], name="date"),
    )

    extended_data = pd.concat([data, future_row])
    features = build_features(extended_data)

    training = features.loc[:last_date].dropna(subset=["quantity"])
    future_inputs = features.loc[[forecast_date], FEATURES]

    if training.empty:
        raise ValueError("No usable training records.")

    model = make_model(
        depth=settings["depth"],
        leaf_size=settings["leaf_size"],
    )

    print("Training the separate demonstration model...")
    model.fit(training[FEATURES], training["quantity"])

    predicted_quantity = float(model.predict(future_inputs)[0])

    forecast = {
        "dataset": "Public external dairy data — Product 1",
        "product": "dairy_product_1",
        "target": "daily_unit_sales",
        "forecast_date": forecast_date.date().isoformat(),
        "predicted_quantity": predicted_quantity,
        "unit": "units",
        "history_end": last_date.date().isoformat(),
        "training_rows": len(training),
        "model": "Random Forest",
        "settings": settings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "actual_quantity": None,
        "note": (
            "External dataset demonstration. No actual value is available "
            "for this forecast date. This is not a local business forecast."
        ),
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Separate names protect the original evaluated model and results.
    model_path = models_dir / "dairy_product_1_demo_forecaster.joblib"
    forecast_path = results_dir / "dairy_product_1_next_day_forecast.json"

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "metadata": forecast,
        },
        model_path,
    )

    with forecast_path.open("w", encoding="utf-8") as output:
        json.dump(forecast, output, indent=2, ensure_ascii=False)

    print()
    print("NEXT-DAY FORECAST — EXTERNAL DATASET")
    print(f"History ends: {last_date.date()}")
    print(f"Forecast date: {forecast_date.date()}")
    print(f"Predicted quantity: {predicted_quantity:,.2f} units")
    print(f"Training records: {len(training)}")
    print("Actual quantity: unavailable")
    print(f"Forecast saved to: {forecast_path}")


if __name__ == "__main__":
    main()