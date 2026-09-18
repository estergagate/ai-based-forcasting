import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


BASE_DIR = Path(__file__).resolve().parents[1]

SOURCE_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "french_bakery"
    / "daily_product_sales.csv"
)

RESULTS_FOLDER = (
    BASE_DIR
    / "data"
    / "results"
    / "french_bakery"
)

MODELS_FOLDER = BASE_DIR / "models"

PRODUCT_NAME = "TRADITIONAL BAGUETTE"

FEATURES = [
    "weekday",
    "month",
    "lag_1",
    "lag_7",
    "lag_14",
    "average_7_days",
    "average_28_days",
]


def calculate_metrics(actual, predicted):
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(
            np.sqrt(mean_squared_error(actual, predicted))
        ),
    }


def create_features(daily_sales):
    frame = daily_sales.copy()

    frame["weekday"] = frame.index.dayofweek
    frame["month"] = frame.index.month

    frame["lag_1"] = frame["quantity_sold"].shift(1)
    frame["lag_7"] = frame["quantity_sold"].shift(7)
    frame["lag_14"] = frame["quantity_sold"].shift(14)

    # Shift first so today's real sales never help predict today.
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

    return frame.dropna()


def make_model(max_depth, min_samples_leaf):
    return RandomForestRegressor(
        n_estimators=300,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=42,
        n_jobs=2,
    )


def main():
    if not SOURCE_FILE.exists():
        print("Prepared bakery data was not found.")
        print(f"Expected location: {SOURCE_FILE}")
        return

    sales = pd.read_csv(
        SOURCE_FILE,
        parse_dates=["date"],
    )

    product_sales = sales[
        sales["article"] == PRODUCT_NAME
    ].copy()

    if product_sales.empty:
        print(f"Product not found: {PRODUCT_NAME}")
        return

    product_sales = (
        product_sales
        .groupby("date", as_index=False)["quantity_sold"]
        .sum()
        .sort_values("date")
    )

    first_date = product_sales["date"].min()
    last_date = product_sales["date"].max()

    # Add zero for dates when this product had no saved sale.
    full_dates = pd.date_range(first_date, last_date, freq="D")

    daily_sales = (
        product_sales
        .set_index("date")["quantity_sold"]
        .reindex(full_dates, fill_value=0)
        .to_frame()
    )

    daily_sales.index.name = "date"

    features = create_features(daily_sales)

    # Final 90 days: fair test set.
    test_start = features.index.max() - pd.Timedelta(days=89)

    # The 90 days before the test set: validation set.
    validation_start = test_start - pd.Timedelta(days=90)
    validation_end = test_start - pd.Timedelta(days=1)

    training_end = validation_start - pd.Timedelta(days=1)

    training = features.loc[:training_end]
    validation = features.loc[
        validation_start:validation_end
    ]
    test = features.loc[test_start:].copy()

    if min(len(training), len(validation), len(test)) < 30:
        raise ValueError(
            "There are not enough daily records for the split."
        )

    candidates = [
        {"max_depth": 6, "min_samples_leaf": 3},
        {"max_depth": 12, "min_samples_leaf": 2},
    ]

    validation_results = []

    print("\nVALIDATION RESULTS\n")

    for settings in candidates:
        model = make_model(**settings)

        model.fit(
            training[FEATURES],
            training["quantity_sold"],
        )

        predicted = model.predict(validation[FEATURES])

        metrics = calculate_metrics(
            validation["quantity_sold"],
            predicted,
        )

        result = {
            **settings,
            **metrics,
        }

        validation_results.append(result)

        print(
            f"Depth {settings['max_depth']}, "
            f"minimum leaf {settings['min_samples_leaf']}: "
            f"MAE = {metrics['mae']:,.2f} units"
        )

    best_settings = min(
        validation_results,
        key=lambda result: result["mae"],
    )

    # Train again using all sales before the final test period.
    development = features.loc[:validation_end]

    final_model = make_model(
        max_depth=best_settings["max_depth"],
        min_samples_leaf=best_settings["min_samples_leaf"],
    )

    final_model.fit(
        development[FEATURES],
        development["quantity_sold"],
    )

    test["baseline"] = test["lag_7"]
    test["random_forest"] = final_model.predict(
        test[FEATURES]
    )

    baseline_metrics = calculate_metrics(
        test["quantity_sold"],
        test["baseline"],
    )

    random_forest_metrics = calculate_metrics(
        test["quantity_sold"],
        test["random_forest"],
    )

    RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
    MODELS_FOLDER.mkdir(parents=True, exist_ok=True)

    comparison_file = (
        RESULTS_FOLDER
        / "traditional_baguette_test_comparison.csv"
    )

    test[
        [
            "quantity_sold",
            "baseline",
            "random_forest",
        ]
    ].rename(
        columns={"quantity_sold": "actual"}
    ).to_csv(comparison_file)

    report = {
        "dataset": "French bakery daily sales from Kaggle",
        "product": PRODUCT_NAME,
        "target": "next_day_quantity_sold",
        "training_period": (
            f"{training.index.min().date()} to "
            f"{training.index.max().date()}"
        ),
        "validation_period": (
            f"{validation.index.min().date()} to "
            f"{validation.index.max().date()}"
        ),
        "test_period": (
            f"{test.index.min().date()} to "
            f"{test.index.max().date()}"
        ),
        "test_days": int(len(test)),
        "baseline": baseline_metrics,
        "random_forest": random_forest_metrics,
        "chosen_settings": {
            "max_depth": best_settings["max_depth"],
            "min_samples_leaf": (
                best_settings["min_samples_leaf"]
            ),
        },
    }

    report_file = (
        RESULTS_FOLDER
        / "traditional_baguette_metrics.json"
    )

    with report_file.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    model_file = (
        MODELS_FOLDER
        / "traditional_baguette_forecast_model.joblib"
    )

    joblib.dump(
        {
            "model": final_model,
            "features": FEATURES,
            "product": PRODUCT_NAME,
            "history_end": str(last_date.date()),
        },
        model_file,
    )

    print("\nFINAL TEST — LAST 90 DAYS\n")
    print(
        f"Baseline: MAE = {baseline_metrics['mae']:,.2f}, "
        f"RMSE = {baseline_metrics['rmse']:,.2f} units"
    )
    print(
        f"Random Forest: "
        f"MAE = {random_forest_metrics['mae']:,.2f}, "
        f"RMSE = {random_forest_metrics['rmse']:,.2f} units"
    )

    if random_forest_metrics["mae"] < baseline_metrics["mae"]:
        print("\nRandom Forest has lower test MAE.")
    else:
        print("\nThe weekly baseline has lower test MAE.")

    print(f"\nModel saved: {model_file}")
    print(f"Results saved: {RESULTS_FOLDER}")


if __name__ == "__main__":
    main()