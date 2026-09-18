import json
import math
import os
import tempfile
from datetime import datetime, timezone

import joblib
import pandas as pd

from .train_forecasting_model import (
    BASE_DIR,
    FEATURES,
    build_features,
    load_data,
)


def generate_demo_forecast():
    model_path = (
        BASE_DIR / "models" / "dairy_product_1_demo_forecaster.joblib"
    )

    if not model_path.exists():
        raise ValueError("The saved dairy demonstration model is missing.")

    bundle = joblib.load(model_path)
    metadata = bundle["metadata"]

    if bundle["features"] != FEATURES:
        raise ValueError("The saved model uses different input features.")

    if metadata["product"] != "dairy_product_1":
        raise ValueError("The saved model is for a different product.")

    data = load_data()
    history_end = data.index.max()
    forecast_date = history_end + pd.Timedelta(days=1)

    if metadata["history_end"] != history_end.date().isoformat():
        raise ValueError("The saved model does not match the current history.")

    for days in (1, 7, 14, 28):
        reference_date = forecast_date - pd.Timedelta(days=days)

        if (
            reference_date not in data.index
            or pd.isna(data.loc[reference_date, "quantity"])
        ):
            raise ValueError(
                f"Missing sales quantity for {reference_date.date()}."
            )

    future_row = pd.DataFrame(
        {"quantity": [float("nan")], "status": ["future"]},
        index=pd.DatetimeIndex([forecast_date], name="date"),
    )

    features = build_features(pd.concat([data, future_row]))
    inputs = features.loc[[forecast_date], FEATURES]

    quantity = float(bundle["model"].predict(inputs)[0])

    if not math.isfinite(quantity) or quantity < 0:
        raise ValueError("The model returned an invalid forecast.")

    forecast = {
        **metadata,
        "forecast_date": forecast_date.date().isoformat(),
        "history_end": history_end.date().isoformat(),
        "predicted_quantity": quantity,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "actual_quantity": None,
    }

    results_dir = BASE_DIR / "data" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    destination = results_dir / "dairy_product_1_next_day_forecast.json"
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=results_dir,
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = output.name
            json.dump(forecast, output, indent=2, ensure_ascii=False)

        os.replace(temporary_path, destination)

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

    return forecast