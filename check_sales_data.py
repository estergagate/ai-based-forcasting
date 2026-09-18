from datetime import datetime, timedelta, timezone

from app import app, get_db


def check_sales_data():
    # Exclude today because its sales may still be incomplete.
    today = datetime.now(timezone(timedelta(hours=8))).date()
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=27)

    with app.app_context():
        with get_db().cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    b.business_name,
                    p.product_name,
                    COUNT(DISTINCT s.sale_date) AS recorded_days,
                    SUM(
                        CASE
                            WHEN s.sale_id IS NOT NULL
                                 AND s.quantity_sold = 0
                            THEN 1
                            ELSE 0
                        END
                    ) AS zero_sales_days,
                    MAX(s.sale_date) AS latest_record
                FROM products AS p
                JOIN businesses AS b
                    ON b.business_id = p.business_id
                LEFT JOIN daily_sales AS s
                    ON s.product_id = p.product_id
                   AND s.sale_date BETWEEN %s AND %s
                GROUP BY
                    b.business_id,
                    b.business_name,
                    p.product_id,
                    p.product_name
                ORDER BY b.business_name, p.product_name
                """,
                (start_date, end_date),
            )

            products = cursor.fetchall()

    print()
    print("SALES DATA CHECK")
    print(f"Period: {start_date} to {end_date}")
    print("Today is excluded.")
    print()

    if not products:
        print("No products found.")
        return

    for product in products:
        recorded_days = product["recorded_days"]
        missing_days = 28 - recorded_days
        latest = product["latest_record"]

        print(f"Business: {product['business_name']}")
        print(f"Product: {product['product_name']}")
        print(f"Days with records: {recorded_days} / 28")
        print(f"Days without records: {missing_days}")
        print(f"Recorded zero-sales days: {product['zero_sales_days']}")
        print(f"Latest record in this period: {latest or 'None'}")
        print("-" * 45)


if __name__ == "__main__":
    check_sales_data()