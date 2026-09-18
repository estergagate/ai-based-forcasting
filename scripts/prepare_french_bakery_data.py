from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

SOURCE_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "french_bakery"
    / "Bakery sales.csv"
)

OUTPUT_FOLDER = (
    BASE_DIR
    / "data"
    / "processed"
    / "french_bakery"
)

DAILY_SALES_FILE = OUTPUT_FOLDER / "daily_product_sales.csv"
PRODUCTS_FILE = OUTPUT_FOLDER / "french_bakery_products.csv"


def clean_price(value):
    """Turn a value such as '0,90 €' into 0.90."""
    if pd.isna(value):
        return None

    text = str(value)
    text = text.replace("€", "")
    text = text.replace("\xa0", "")
    text = text.replace(",", ".")
    text = text.strip()

    return pd.to_numeric(text, errors="coerce")


def main():
    if not SOURCE_FILE.exists():
        print("The source CSV file was not found.")
        print(f"Expected location: {SOURCE_FILE}")
        return

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    sales = pd.read_csv(SOURCE_FILE)

    # The first unnamed column is only the original CSV row number.
    sales = sales.loc[
        :,
        ~sales.columns.astype(str).str.startswith("Unnamed")
    ]

    required_columns = {
        "date",
        "ticket_number",
        "article",
        "Quantity",
        "unit_price",
    }

    missing_columns = required_columns - set(sales.columns)

    if missing_columns:
        print("The CSV is missing these required columns:")
        print(", ".join(sorted(missing_columns)))
        return

    source_records = len(sales)

    sales["date"] = pd.to_datetime(
        sales["date"],
        errors="coerce",
    )

    sales["article"] = (
        sales["article"]
        .astype("string")
        .str.strip()
    )

    sales["Quantity"] = pd.to_numeric(
        sales["Quantity"],
        errors="coerce",
    )

    sales["unit_price_eur"] = sales["unit_price"].apply(
        clean_price
    )

    valid_sales = sales[
        sales["date"].notna()
        & sales["article"].notna()
        & sales["article"].ne("")
        & sales["Quantity"].notna()
        & sales["Quantity"].gt(0)
    ].copy()

    removed_records = source_records - len(valid_sales)

    # Combine individual transactions into daily sales per product.
    daily_sales = (
        valid_sales
        .groupby(
            ["date", "article"],
            as_index=False,
        )
        .agg(
            quantity_sold=("Quantity", "sum"),
            average_unit_price_eur=(
                "unit_price_eur",
                "median",
            ),
            transaction_lines=("ticket_number", "size"),
        )
        .sort_values(["article", "date"])
    )

    daily_sales.to_csv(
        DAILY_SALES_FILE,
        index=False,
        encoding="utf-8",
    )

    products = (
        daily_sales
        .groupby("article", as_index=False)
        .agg(
            total_quantity_sold=(
                "quantity_sold",
                "sum",
            ),
            days_with_sales=("date", "nunique"),
            first_sale_date=("date", "min"),
            last_sale_date=("date", "max"),
            typical_price_eur=(
                "average_unit_price_eur",
                "median",
            ),
        )
        .sort_values(
            "total_quantity_sold",
            ascending=False,
        )
    )

    products.to_csv(
        PRODUCTS_FILE,
        index=False,
        encoding="utf-8",
    )

    print("\nFRENCH BAKERY DATA PREPARED\n")
    print(f"Source records: {source_records:,}")
    print(f"Removed invalid or return records: {removed_records:,}")
    print(f"Daily product records: {len(daily_sales):,}")
    print(f"Products found: {len(products):,}")
    print(f"\nCreated: {DAILY_SALES_FILE}")
    print(f"Created: {PRODUCTS_FILE}")

    print("\nTop 10 products by quantity sold:")
    print(
        products[
            [
                "article",
                "total_quantity_sold",
                "days_with_sales",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()