import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "processed"
RESULTS_DIR = BASE_DIR / "data" / "results"
MODELS_DIR = BASE_DIR / "models"

FEATURES = [
    "weekday",
    "month",
    "day_of_year",
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "mean_7",
    "mean_28",
    "observed_7",
    "observed_28",
]


def load_data():
    frames = []

    for filename, expected_years in [
        ("dairy_product_1_train.csv", {2020, 2021}),
        ("dairy_product_1_test.csv", {2022}),
    ]:
        frame = pd.read_csv(
            DATA_DIR / filename,
            parse_dates=["date"],
        )

        if frame["date"].isna().any():
            raise ValueError(f"Invalid dates in {filename}")

        if not frame["date"].dt.year.isin(expected_years).all():
            raise ValueError(f"Unexpected years in {filename}")

        frame["quantity"] = pd.to_numeric(
            frame["quantity"], errors="raise"
        )

        # Only approved observations can be training targets.
        frame.loc[
            frame["status"] != "recorded", "quantity"
        ] = np.nan

        valid = frame["quantity"].dropna()

        if not np.isfinite(valid).all() or (valid < 0).any():
            raise ValueError(f"Invalid quantities in {filename}")

        frames.append(frame)

    data = pd.concat(frames).sort_values("date")

    if data["date"].duplicated().any():
        raise ValueError("Duplicate dates found.")

    data = data.set_index("date")

    # Preserve calendar gaps so a lag means calendar days.
    calendar = pd.date_range("2020-01-01", "2022-12-31")
    data = data.reindex(calendar)
    data.index.name = "date"

    return data


def build_features(data):
    frame = data.copy()

    frame["weekday"] = frame.index.dayofweek
    frame["month"] = frame.index.month
    frame["day_of_year"] = frame.index.dayofyear

    for days in (1, 7, 14, 28):
        frame[f"lag_{days}"] = frame["quantity"].shift(days)

    # Shift first: today's actual sales must not enter its inputs.
    past_sales = frame["quantity"].shift(1)

    for days in (7, 28):
        window = past_sales.rolling(days, min_periods=1)
        frame[f"mean_{days}"] = window.mean()
        frame[f"observed_{days}"] = window.count()

    # Allow a 28-day history before the first training target.
    return frame.loc["2020-01-29":]


def make_model(depth, leaf_size):
    return Pipeline([
        (
            "imputer",
            SimpleImputer(strategy="median", add_indicator=True),
        ),
        (
            "forest",
            RandomForestRegressor(
                n_estimators=200,
                max_depth=depth,
                min_samples_leaf=leaf_size,
                random_state=42,
                n_jobs=2,
            ),
        ),
    ])


def calculate_metrics(actual, predicted):
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(
            np.sqrt(mean_squared_error(actual, predicted))
        ),
    }


def main():
    frame = build_features(load_data())

    training = frame.loc["2020"].dropna(subset=["quantity"])
    validation = frame.loc["2021"].dropna(subset=["quantity"])

    if training.empty or validation.empty:
        raise ValueError("Training and validation records are required.")

    candidates = [
        {"depth": 6, "leaf_size": 5},
        {"depth": 12, "leaf_size": 3},
    ]

    validation_results = []

    print("VALIDATION — 2021")

    for settings in candidates:
        model = make_model(**settings)
        model.fit(training[FEATURES], training["quantity"])

        predictions = model.predict(validation[FEATURES])
        metrics = calculate_metrics(
            validation["quantity"], predictions
        )

        result = {**settings, **metrics}
        validation_results.append(result)

        print(
            f"Depth {settings['depth']}, "
            f"leaf size {settings['leaf_size']}: "
            f"MAE = {metrics['mae']:,.2f}"
        )

    # Select using validation MAE, never test performance.
    best = min(validation_results, key=lambda item: item["mae"])
    chosen_settings = {
        "depth": best["depth"],
        "leaf_size": best["leaf_size"],
    }

    # Refit with both earlier years before final testing.
    development = frame.loc[:"2021-12-31"].dropna(
        subset=["quantity"]
    )

    model = make_model(**chosen_settings)
    model.fit(development[FEATURES], development["quantity"])

    test = frame.loc["2022"].copy()
    test["random_forest"] = model.predict(test[FEATURES])
    test["baseline"] = test["lag_7"]

    # Both methods are evaluated on exactly the same dates.
    eligible = test["quantity"].notna() & test["baseline"].notna()
    comparison = test.loc[eligible].copy()

    if comparison.empty:
        raise ValueError("No common test dates are available.")

    baseline_metrics = calculate_metrics(
        comparison["quantity"], comparison["baseline"]
    )
    forest_metrics = calculate_metrics(
        comparison["quantity"], comparison["random_forest"]
    )

    test["evaluated"] = eligible
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    test[[
        "quantity", "baseline", "random_forest", "evaluated"
    ]].rename(
        columns={"quantity": "actual"}
    ).to_csv(
        RESULTS_DIR / "dairy_product_1_model_comparison.csv"
    )

    report = {
        "dataset": "Public external dairy data — Product 1",
        "target": "daily_unit_sales",
        "evaluation": "Rolling one-day-ahead; actual prior days available",
        "training_end": "2021-12-31",
        "test_period": "2022-01-01 to 2022-12-31",
        "evaluated_days": len(comparison),
        "skipped_days": len(test) - len(comparison),
        "validation_results": validation_results,
        "chosen_settings": chosen_settings,
        "baseline": baseline_metrics,
        "random_forest": forest_metrics,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
    }

    with (RESULTS_DIR / "dairy_product_1_metrics.json").open(
        "w", encoding="utf-8"
    ) as output:
        json.dump(report, output, indent=2)

    # Save the evaluated model, still trained only through 2021.
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "metadata": report,
        },
        MODELS_DIR / "dairy_product_1_random_forest.joblib",
    )

    print("\nFINAL TEST — 2022")
    print(f"Evaluated dates: {len(comparison)}")
    print(f"Skipped dates: {len(test) - len(comparison)}")

    for name, metrics in [
        ("Baseline", baseline_metrics),
        ("Random Forest", forest_metrics),
    ]:
        print(
            f"{name}: MAE = {metrics['mae']:,.2f}, "
            f"RMSE = {metrics['rmse']:,.2f} units"
        )

    if forest_metrics["mae"] < baseline_metrics["mae"]:
        print("Random Forest has lower test MAE.")
    else:
        print("Random Forest did not improve on baseline test MAE.")

    print("Model and evaluation files saved.")


if __name__ == "__main__":
    main()