import csv
import math
from datetime import date, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "data" / "results"


def load_records(filename):
    records = {}

    with (DATA_DIR / filename).open(
        newline="", encoding="utf-8"
    ) as source:
        for row in csv.DictReader(source):
            sales_date = date.fromisoformat(row["date"])

            if sales_date in records:
                raise ValueError(f"Duplicate date: {sales_date}")

            quantity = None

            if row["status"] == "recorded" and row["quantity"] != "":
                quantity = float(row["quantity"])

                if not math.isfinite(quantity) or quantity < 0:
                    raise ValueError(
                        f"Invalid quantity on {sales_date}"
                    )

            records[sales_date] = quantity

    return records


def evaluate_baseline():
    training = load_records("dairy_product_1_train.csv")
    testing = load_records("dairy_product_1_test.csv")

    if not training or not testing:
        raise ValueError("Training and testing files must contain data.")

    if max(training) >= min(testing):
        raise ValueError("Training dates must come before testing dates.")

    history = dict(training)
    results = []
    absolute_errors = []
    squared_errors = []

    for sales_date in sorted(testing):
        actual = testing[sales_date]
        reference_date = sales_date - timedelta(days=7)
        predicted = history.get(reference_date)

        if actual is None:
            status = "missing_actual"
            absolute_error = ""

        elif predicted is None:
            status = "missing_reference"
            absolute_error = ""

        else:
            status = "evaluated"
            absolute_error = abs(actual - predicted)

            absolute_errors.append(absolute_error)
            squared_errors.append((actual - predicted) ** 2)

        results.append({
            "date": sales_date.isoformat(),
            "reference_date": reference_date.isoformat(),
            "actual": actual if actual is not None else "",
            "predicted": predicted if predicted is not None else "",
            "absolute_error": absolute_error,
            "status": status,
        })

        # After this day's prediction, its actual value becomes
        # available for predictions on later dates.
        history[sales_date] = actual

    if not absolute_errors:
        raise ValueError("No dates could be evaluated.")

    mae = sum(absolute_errors) / len(absolute_errors)
    rmse = math.sqrt(sum(squared_errors) / len(squared_errors))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "dairy_product_1_baseline.csv"

    with output_path.open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "date",
                "reference_date",
                "actual",
                "predicted",
                "absolute_error",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print("SEVEN-DAY BASELINE")
    print("Evaluation: one-day-ahead predictions")
    print(f"Test dates: {len(testing)}")
    print(f"Evaluated dates: {len(absolute_errors)}")
    print(f"Skipped dates: {len(testing) - len(absolute_errors)}")
    print(f"MAE: {mae:,.2f} units")
    print(f"RMSE: {rmse:,.2f} units")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    evaluate_baseline()