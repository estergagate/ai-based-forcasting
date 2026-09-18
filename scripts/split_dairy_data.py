import csv
import math
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "processed"
INPUT_FILE = DATA_DIR / "dairy_product_1_review.csv"


def split_data():
    training_rows = []
    testing_rows = []
    seen_dates = set()

    with INPUT_FILE.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            sales_date = date.fromisoformat(row["date"])

            if sales_date in seen_dates:
                raise ValueError(f"Duplicate date: {sales_date}")

            seen_dates.add(sales_date)

            # Flagged observations stay blank, not zero.
            quantity = ""

            if row["status"] == "recorded":
                quantity = float(row["quantity"])

                if not math.isfinite(quantity) or quantity < 0:
                    raise ValueError(
                        f"Invalid recorded quantity on {sales_date}"
                    )

            prepared_row = {
                "date": sales_date.isoformat(),
                "quantity": quantity,
                "status": row["status"],
            }

            if date(2020, 1, 1) <= sales_date < date(2022, 1, 1):
                training_rows.append(prepared_row)

            elif date(2022, 1, 1) <= sales_date <= date(2022, 12, 31):
                testing_rows.append(prepared_row)

            else:
                raise ValueError(f"Unexpected date: {sales_date}")

    if not training_rows or not testing_rows:
        raise ValueError("Both training and testing data are required.")

    datasets = [
        ("dairy_product_1_train.csv", training_rows),
        ("dairy_product_1_test.csv", testing_rows),
    ]

    for filename, rows in datasets:
        rows.sort(key=lambda row: row["date"])
        output_path = DATA_DIR / filename

        with output_path.open(
            "w", newline="", encoding="utf-8"
        ) as output:
            writer = csv.DictWriter(
                output,
                fieldnames=["date", "quantity", "status"],
            )
            writer.writeheader()
            writer.writerows(rows)

        usable = sum(row["quantity"] != "" for row in rows)

        print(filename)
        print(f"  Calendar days: {len(rows)}")
        print(f"  Usable quantities: {usable}")
        print(f"  Flagged quantities: {len(rows) - usable}")
        print()

    print("Split complete. No model has been trained yet.")


if __name__ == "__main__":
    split_data()