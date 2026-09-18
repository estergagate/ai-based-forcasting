import os
import secrets
import csv
import io
import json
import math
from functools import wraps
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

import pymysql
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    send_from_directory,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR),
    static_folder=str(BASE_DIR / "css"),
    static_url_path="/css",
)

# Load saved HTML changes while developing the system.
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Store a private session-signing key locally.
instance_dir = BASE_DIR / "instance"
instance_dir.mkdir(exist_ok=True)

key_file = instance_dir / "secret-key.txt"

if not key_file.exists():
    key_file.write_text(
        secrets.token_hex(32),
        encoding="utf-8",
    )

app.config.update(
    SECRET_KEY=key_file.read_text(encoding="utf-8").strip(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host="127.0.0.1",
            user="root",
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database="ai_sales_system",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    database = g.pop("db", None)

    if database is not None:
        database.close()


@app.before_request
def load_user():
    g.user = None

    user_id = session.get("user_id")

    if user_id is not None:
        with get_db().cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, username, role
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )

            g.user = cursor.fetchone()

        if g.user is None:
            session.clear()


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))

        if g.user["role"] != "Admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view

def business_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))

        if g.user["role"] != "Business":
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


def validate_csrf():
    expected = session.get("csrf_token", "")
    received = request.form.get("csrf_token", "")

    if not expected or not secrets.compare_digest(expected, received):
        abort(
            400,
            description="The form expired. Reload the page and try again.",
        )


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        validate_csrf()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db().cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, username, password_hash, role
                FROM users
                WHERE username = %s
                """,
                (username,),
            )

            user = cursor.fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password,
        ):
            if user["role"] in ("Admin", "Business"):
                session.clear()
                session["user_id"] = user["user_id"]

                if user["role"] == "Admin":
                    return redirect(url_for("admin_dashboard"))

                return redirect(url_for("business_dashboard"))

            error = "This account does not have access to the system."
        else:
            error = "Incorrect username or password."

    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        if g.user["role"] == "Admin":
            return redirect(url_for("admin_dashboard"))

        return redirect(url_for("business_dashboard"))

    error = None
    values = {
        "business_name": "",
        "business_type": "",
        "username": "",
    }

    if request.method == "POST":
        validate_csrf()

        values = {
            field: request.form.get(field, "").strip()
            for field in values
        }

        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")

        if not 1 <= len(values["business_name"]) <= 100:
            error = "Enter your business name using up to 100 characters."

        elif values["business_type"] not in (
            "Bakery", "Carinderia", "Food Stall"
        ):
            error = "Please choose your type of business."

        elif not 1 <= len(values["username"]) <= 50:
            error = "Choose a username using up to 50 characters."

        elif any(char.isspace() for char in values["username"]):
            error = "Your username cannot contain spaces."

        elif not 12 <= len(password) <= 128:
            error = "Use a password between 12 and 128 characters."

        elif password != confirmation:
            error = "Your passwords do not match. Please enter them again."

        if error is None:
            password_hash = generate_password_hash(password)
            database = None

            try:
                database = get_db()
                database.begin()

                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (username, password_hash, role)
                        VALUES (%s, %s, 'Business')
                        """,
                        (values["username"], password_hash),
                    )

                    user_id = cursor.lastrowid

                    cursor.execute(
                        """
                        INSERT INTO businesses (
                            user_id, business_name, business_type
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            user_id,
                            values["business_name"],
                            values["business_type"],
                        ),
                    )

                database.commit()

            except pymysql.MySQLError as database_error:
                if database is not None:
                    database.rollback()

                if database_error.args[0] == 1062:
                    error = (
                        "That username is already in use. "
                        "Please choose another one."
                    )
                else:
                    app.logger.exception("Business registration failed.")
                    error = (
                        "We couldn't create your account right now. "
                        "Please try again."
                    )

            else:
                flash(
                    "Your account is ready! Sign in with your new "
                    "username and password.",
                    "registration_success",
                )
                return redirect(url_for("login"))

    return render_template(
        "register.html",
        error=error,
        values=values,
    )

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    with get_db().cursor() as cursor:
        cursor.execute(
    """
    SELECT
        users.user_id,
        users.username,
        users.created_at,
        businesses.business_name,
        businesses.business_type
    FROM users
    LEFT JOIN businesses
        ON businesses.user_id = users.user_id
    WHERE users.role = 'Business'
    ORDER BY users.created_at DESC, users.user_id DESC
    """
)

        business_accounts = cursor.fetchall()

    return render_template(
        "admin/dashboard.html",
        business_accounts=business_accounts,
        business_count=len(business_accounts),
    )


@app.route("/logout", methods=["POST"])
def logout():
    validate_csrf()
    session.clear()

    return redirect(url_for("login"))

@app.route("/admin/businesses/add", methods=["GET", "POST"])
@admin_required
def add_business():
    error = None

    values = {
        "business_name": "",
        "business_type": "",
        "username": "",
    }

    if request.method == "POST":
        validate_csrf()

        values = {
            "business_name": request.form.get(
                "business_name", ""
            ).strip(),
            "business_type": request.form.get(
                "business_type", ""
            ).strip(),
            "username": request.form.get(
                "username", ""
            ).strip(),
        }

        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")

        allowed_types = ("Bakery", "Carinderia", "Food Stall")

        if not 1 <= len(values["business_name"]) <= 100:
            error = "Enter a business name between 1 and 100 characters."

        elif values["business_type"] not in allowed_types:
            error = "Select a valid business type."

        elif not 1 <= len(values["username"]) <= 50:
            error = "Enter a username between 1 and 50 characters."

        elif any(character.isspace() for character in values["username"]):
            error = "The username cannot contain spaces."

        elif len(password) < 12:
            error = "Use a password of at least 12 characters."

        elif password != confirmation:
            error = "The passwords do not match."

        if error is None:
            password_hash = generate_password_hash(password)
            database = get_db()

            try:
                database.begin()

                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (
                            username,
                            password_hash,
                            role
                        )
                        VALUES (%s, %s, 'Business')
                        """,
                        (
                            values["username"],
                            password_hash,
                        ),
                    )

                    user_id = cursor.lastrowid

                    cursor.execute(
                        """
                        INSERT INTO businesses (
                            user_id,
                            business_name,
                            business_type
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            user_id,
                            values["business_name"],
                            values["business_type"],
                        ),
                    )

                database.commit()

                return redirect(url_for("admin_dashboard"))

            except pymysql.err.IntegrityError as database_error:
                database.rollback()

                if database_error.args[0] == 1062:
                    error = "That username is already taken."
                else:
                    app.logger.exception(
                        "Business account creation failed."
                    )
                    error = "The account could not be saved."

            except pymysql.MySQLError:
                database.rollback()

                app.logger.exception(
                    "Database error while creating a business."
                )

                error = (
                    "The account could not be saved. "
                    "Please try again."
                )

    return render_template(
        "admin/add_business.html",
        error=error,
        values=values,
    )

@app.route("/business/forecasting")
@business_required
def business_forecasting():
    with get_db().cursor() as cursor:
        cursor.execute(
            """
        SELECT
            business_id,
            business_name,
            business_type,
            created_at,
            location_latitude,
            location_longitude,
            location_name,
            location_accuracy_m,
            location_updated_at
        FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

    if business is None:
        abort(403, description="Your account has no linked business.")

    results_folder = (
        BASE_DIR
        / "data"
        / "results"
        / "french_bakery"
    )

    forecast = None
    forecast_error = None
    model_report = None
    model_error = None

    try:
        forecast_file = (
            results_folder
            / "traditional_baguette_next_day_forecast.json"
        )

        with forecast_file.open(encoding="utf-8") as file:
            saved_forecast = json.load(file)

        quantity = float(saved_forecast["predicted_quantity"])

        if not math.isfinite(quantity) or quantity < 0:
            raise ValueError("Invalid predicted quantity.")

        forecast_date = date.fromisoformat(
            saved_forecast["forecast_date"]
        )

        history_end = date.fromisoformat(
            saved_forecast["history_end"]
        )

        if forecast_date != history_end + timedelta(days=1):
            raise ValueError("Forecast date is invalid.")

        if saved_forecast["product"] != "TRADITIONAL BAGUETTE":
            raise ValueError("Unexpected forecast product.")

        forecast = {
            "product": "Traditional Baguette",
            "quantity": quantity,
            "unit": saved_forecast["unit"],
            "forecast_date": forecast_date,
            "history_end": history_end,
            "training_records": int(
                saved_forecast["training_records"]
            ),
        }

    except FileNotFoundError:
        forecast_error = (
            "No bakery forecast was found. "
            "Run generate_french_bakery_forecast.py first."
        )

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        app.logger.exception("Could not load French bakery forecast.")

        forecast_error = (
            "The bakery forecast could not be loaded."
        )

    try:
        report_file = (
            results_folder
            / "traditional_baguette_metrics.json"
        )

        with report_file.open(encoding="utf-8") as file:
            model_report = json.load(file)

        for method in ("baseline", "random_forest"):
            for metric in ("mae", "rmse"):
                model_report[method][metric] = float(
                    model_report[method][metric]
                )

        model_report["test_days"] = int(
            model_report["test_days"]
        )

    except FileNotFoundError:
        model_error = "Model test results are not available yet."

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        app.logger.exception("Could not load bakery model results.")

        model_error = (
            "Model test results could not be loaded."
        )

    weather = None
    weather_error = None

    if (
        business["location_latitude"] is not None
        and business["location_longitude"] is not None
    ):
        try:
            weather = get_business_weather(
                float(business["location_latitude"]),
                float(business["location_longitude"]),
            )

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ):
            app.logger.exception(
                "Could not load the business weather."
            )

            weather_error = (
                "The latest weather could not be loaded. "
                "Please refresh the page later."
            )

    return render_template(
        "business/forecasting.html",
        business=business,
        forecast=forecast,
        forecast_error=forecast_error,
        model_report=model_report,
        model_error=model_error,
        weather=weather,
        weather_error=weather_error,
    )

def describe_weather(code):
    if code == 0:
        return {"text": "Clear", "icon": "☀️"}

    if code in (1, 2):
        return {"text": "Partly cloudy", "icon": "⛅"}

    if code == 3:
        return {"text": "Cloudy", "icon": "☁️"}

    if code in (45, 48):
        return {"text": "Foggy", "icon": "🌫️"}

    if code in (51, 53, 55, 56, 57):
        return {"text": "Drizzle", "icon": "🌦️"}

    if code in (61, 63, 66, 80, 81):
        return {"text": "Rain", "icon": "🌧️"}

    if code in (65, 67, 82):
        return {"text": "Heavy rain", "icon": "⛈️"}

    if code in (95, 96, 99):
        return {"text": "Thunderstorm", "icon": "⛈️"}

    return {
        "text": "Weather unavailable",
        "icon": "🌤️",
    }


def find_location_name(latitude, longitude):
    parameters = urlencode({
        "format": "jsonv2",
        "lat": latitude,
        "lon": longitude,
        "zoom": 10,
        "addressdetails": 1,
    })

    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + parameters
    )

    location_request = UrlRequest(
        url,
        headers={
            "User-Agent": (
                "FoodCastAI-Research/1.0 "
                "(student research project)"
            ),
            "Accept-Language": "en",
        },
    )

    with urlopen(location_request, timeout=6) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    address = result.get("address", {})

    locality = (
        address.get("city")
        or address.get("municipality")
        or address.get("town")
        or address.get("village")
        or address.get("county")
    )

    region = (
        address.get("state")
        or address.get("region")
    )

    parts = []

    for part in (locality, region):
        if part and part not in parts:
            parts.append(part)

    if parts:
        return ", ".join(parts)

    return "Saved business location"


def get_business_weather(latitude, longitude):
    parameters = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "precipitation_sum,"
            "wind_speed_10m_max"
        ),
        "timezone": "Asia/Manila",
        "forecast_days": 2,
    })

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + parameters
    )

    weather_request = UrlRequest(
        url,
        headers={
            "User-Agent": (
                "FoodCastAI-Research/1.0 "
                "(student research project)"
            ),
        },
    )

    with urlopen(weather_request, timeout=6) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    current = result["current"]
    daily = result["daily"]

    if len(daily["time"]) < 2:
        raise ValueError(
            "Tomorrow's weather is unavailable."
        )

    today_condition = describe_weather(
        int(current["weather_code"])
    )

    tomorrow_code = int(
        daily["weather_code"][1]
    )

    tomorrow_condition = describe_weather(
        tomorrow_code
    )

    tomorrow_rain_chance = float(
        daily["precipitation_probability_max"][1]
    )

    tomorrow_rain_amount = float(
        daily["precipitation_sum"][1]
    )

    severe_codes = {
        65,
        67,
        82,
        95,
        96,
        99,
    }

    if (
        tomorrow_code in severe_codes
        or tomorrow_rain_amount >= 20
    ):
        advice = (
            "Heavy rain may affect customer visits tomorrow. "
            "Consider preparing smaller batches first and "
            "check official class or local announcements."
        )

        advice_level = "high"

    elif (
        tomorrow_rain_chance >= 60
        or tomorrow_rain_amount >= 5
    ):
        advice = (
            "Rain is possible tomorrow. Consider preparing "
            "food in smaller batches so you can adjust "
            "during the day."
        )

        advice_level = "medium"

    else:
        advice = (
            "No high rain risk is currently shown for "
            "tomorrow. Continue checking the forecast "
            "before preparing stock."
        )

        advice_level = "normal"

    updated_time = datetime.fromisoformat(
        current["time"]
    ).strftime("%I:%M %p")

    return {
        "updated_time": updated_time,

        "today": {
            "icon": today_condition["icon"],
            "condition": today_condition["text"],
            "temperature": round(
                float(current["temperature_2m"])
            ),
            "humidity": round(
                float(current["relative_humidity_2m"])
            ),
            "wind": round(
                float(current["wind_speed_10m"])
            ),
            "rain_chance": round(
                float(
                    daily[
                        "precipitation_probability_max"
                    ][0]
                )
            ),
        },

        "tomorrow": {
            "icon": tomorrow_condition["icon"],
            "condition": tomorrow_condition["text"],
            "maximum_temperature": round(
                float(
                    daily["temperature_2m_max"][1]
                )
            ),
            "minimum_temperature": round(
                float(
                    daily["temperature_2m_min"][1]
                )
            ),
            "rain_chance": round(
                tomorrow_rain_chance
            ),
            "rain_amount": round(
                tomorrow_rain_amount,
                1,
            ),
        },

        "advice": advice,
        "advice_level": advice_level,
    }

@app.route("/business/location", methods=["POST"])
@business_required
def save_business_location():
    validate_csrf()

    try:
        latitude = float(request.form.get("latitude", ""))
        longitude = float(request.form.get("longitude", ""))
        accuracy = float(request.form.get("accuracy", ""))
    except ValueError:
        abort(400, description="The location information is invalid.")

    if not -90 <= latitude <= 90:
        abort(400, description="The latitude is invalid.")

    if not -180 <= longitude <= 180:
        abort(400, description="The longitude is invalid.")

    if not 0 <= accuracy <= 100000:
        abort(400, description="The location accuracy is invalid.")

    try:
        location_name = find_location_name(
            latitude,
            longitude,
        )
    except (OSError, ValueError, KeyError, TypeError):
        app.logger.exception(
            "Could not find the readable location name."
        )

        location_name = "Saved business location"

    with get_db().cursor() as cursor:
        cursor.execute(
            """
            UPDATE businesses
            SET
                location_latitude = %s,
                location_longitude = %s,
                location_name = %s,
                location_accuracy_m = %s,
                location_updated_at = NOW()
            WHERE user_id = %s
            """,
            (
                round(latitude, 6),
                round(longitude, 6),
                location_name,
                round(accuracy),
                g.user["user_id"],
            ),
        )

    flash(
        "Your business location was saved.",
        "location_success",
    )

    return_to = request.form.get("return_to", "")

    if return_to == "forecasting":
        return redirect(
            url_for("business_forecasting")
        )

    return redirect(
        url_for("business_dashboard")
    )

@app.route("/business/tips")
@business_required
def business_tips():
    today = datetime.now(
        timezone(timedelta(hours=8))
    ).date()

    recent_start = today - timedelta(days=6)

    with get_db().cursor() as cursor:
        cursor.execute(
            """
            SELECT
                business_id,
                business_name,
                business_type,
                created_at
            FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

        if business is None:
            abort(
                403,
                description="Your account has no linked business.",
            )

        cursor.execute(
            """
            SELECT COUNT(*) AS product_count
            FROM products
            WHERE business_id = %s
            """,
            (business["business_id"],),
        )

        product_count = cursor.fetchone()["product_count"]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT daily_sales.sale_date) AS recorded_days
            FROM daily_sales
            INNER JOIN products
                ON products.product_id = daily_sales.product_id
            WHERE products.business_id = %s
              AND daily_sales.sale_date BETWEEN %s AND %s
            """,
            (
                business["business_id"],
                recent_start,
                today,
            ),
        )

        recorded_days = cursor.fetchone()["recorded_days"]

        cursor.execute(
            """
            SELECT
                products.product_name,
                products.selling_unit,
                SUM(daily_sales.quantity_sold) AS quantity_sold,
                SUM(daily_sales.sales_amount) AS sales_amount
            FROM daily_sales
            INNER JOIN products
                ON products.product_id = daily_sales.product_id
            WHERE products.business_id = %s
              AND daily_sales.sale_date BETWEEN %s AND %s
            GROUP BY
                products.product_id,
                products.product_name,
                products.selling_unit
            HAVING SUM(daily_sales.quantity_sold) > 0
            ORDER BY quantity_sold DESC
            LIMIT 1
            """,
            (
                business["business_id"],
                recent_start,
                today,
            ),
        )

        top_product = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                products.product_name,
                products.selling_unit,
                COALESCE(
                    SUM(
                        CASE
                            WHEN stock_movements.movement_type IN (
                                'Stock In',
                                'Adjustment In'
                            )
                            THEN stock_movements.quantity
                            ELSE -stock_movements.quantity
                        END
                    ),
                    0
                ) AS available
            FROM products
            LEFT JOIN stock_movements
                ON stock_movements.product_id = products.product_id
            WHERE products.business_id = %s
            GROUP BY
                products.product_id,
                products.product_name,
                products.selling_unit
            HAVING available <= 5
            ORDER BY available, products.product_name
            LIMIT 3
            """,
            (business["business_id"],),
        )

        low_stock_products = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(stock_movements.quantity), 0) AS wasted_quantity
            FROM stock_movements
            INNER JOIN products
                ON products.product_id = stock_movements.product_id
            WHERE products.business_id = %s
              AND stock_movements.movement_type = 'Waste'
              AND DATE(stock_movements.created_at)
                  BETWEEN %s AND %s
            """,
            (
                business["business_id"],
                recent_start,
                today,
            ),
        )

        wasted_quantity = cursor.fetchone()["wasted_quantity"]

    tips = []

    if product_count == 0:
        tips.append({
            "icon": "products",
            "title": "Add your products",
            "message": (
                "Add the food items you sell before recording sales "
                "and stock."
            ),
            "level": "attention",
            "endpoint": "business_products",
            "link_text": "Add products",
        })

    elif recorded_days == 0:
        tips.append({
            "icon": "sales",
            "title": "Start recording sales",
            "message": (
                "No sales have been recorded during the last seven days. "
                "Daily records help FoodCast understand your business."
            ),
            "level": "attention",
            "endpoint": "business_sales",
            "link_text": "Record sales",
        })

    elif recorded_days < 7:
        tips.append({
            "icon": "records",
            "title": "Complete your daily sales",
            "message": (
                f"You recorded sales on {recorded_days} of the last "
                "7 days. Record every day, including zero-sales days, "
                "to improve future estimates."
            ),
            "level": "info",
            "endpoint": "business_sales",
            "link_text": "View sales",
        })

    else:
        tips.append({
            "icon": "records",
            "title": "Your sales records are up to date",
            "message": (
                "You have sales records for all seven recent days. "
                "Continue recording sales every day."
            ),
            "level": "positive",
            "endpoint": "business_sales",
            "link_text": "View sales",
        })

    if low_stock_products:
        product_names = ", ".join(
            product["product_name"]
            for product in low_stock_products
        )

        tips.append({
            "icon": "stock",
            "title": "Check these low-stock products",
            "message": (
                f"{product_names} currently have five or fewer units "
                "available. Check whether you need to add stock."
            ),
            "level": "attention",
            "endpoint": "business_inventory",
            "link_text": "Check stock",
        })

    if top_product is not None:
        tips.append({
            "icon": "best-seller",
            "title": "Your recent best seller",
            "message": (
                f"{top_product['product_name']} sold the most during "
                f"the last seven days, with "
                f"{top_product['quantity_sold']:,.0f} "
                f"{top_product['selling_unit'].lower()} sold. "
                "Keep enough stock available for this product."
            ),
            "level": "positive",
            "endpoint": "business_sales",
            "link_text": "View sales",
        })

    if wasted_quantity > 0:
        tips.append({
            "icon": "waste",
            "title": "Review recently wasted stock",
            "message": (
                f"{wasted_quantity:,.0f} units were recorded as waste "
                "during the last seven days. Consider preparing smaller "
                "batches and adding more only when needed."
            ),
            "level": "attention",
            "endpoint": "business_inventory",
            "link_text": "View stock updates",
        })

    return render_template(
        "business/tips.html",
        business=business,
        tips=tips,
        today=today,
        recent_start=recent_start,
    )

@app.route("/business/dashboard")
@business_required
def business_dashboard():
    today = datetime.now(
        timezone(timedelta(hours=8))
    ).date()

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    with get_db().cursor() as cursor:
        cursor.execute(
            """
SELECT
    business_id,
    business_name,
    business_type,
    created_at,
    location_latitude,
    location_longitude,
    location_name,
    location_accuracy_m,
    location_updated_at
FROM businesses

            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

    chart_start = today - timedelta(days=6)

    with get_db().cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        CASE
                            WHEN daily_sales.sale_date = %s
                            THEN daily_sales.sales_amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS today_sales,

                COALESCE(
                    SUM(
                        CASE
                            WHEN daily_sales.sale_date BETWEEN %s AND %s
                            THEN daily_sales.sales_amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS week_sales,

                COALESCE(
                    SUM(
                        CASE
                            WHEN daily_sales.sale_date BETWEEN %s AND %s
                            THEN daily_sales.sales_amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS month_sales

            FROM daily_sales
            INNER JOIN products
                ON products.product_id = daily_sales.product_id

            WHERE products.business_id = %s
              AND daily_sales.sale_date BETWEEN %s AND %s
            """,
            (
                today,
                week_start,
                today,
                month_start,
                today,
                business["business_id"],
                min(week_start, month_start),
                today,
            ),
        )

        totals = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                daily_sales.sale_date,
                SUM(daily_sales.sales_amount) AS amount
            FROM daily_sales
            JOIN products
                ON products.product_id = daily_sales.product_id
            WHERE products.business_id = %s
              AND daily_sales.sale_date BETWEEN %s AND %s
            GROUP BY daily_sales.sale_date
            ORDER BY daily_sales.sale_date
            """,
            (business["business_id"], chart_start, today),
        )

        daily_amounts = {
            row["sale_date"]: row["amount"]
            for row in cursor.fetchall()
        }

    weather = None
    weather_error = None

    if (
        business["location_latitude"] is not None
        and business["location_longitude"] is not None
    ):
        try:
            weather = get_business_weather(
                float(business["location_latitude"]),
                float(business["location_longitude"]),
            )
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ):
            app.logger.exception(
                "Could not load the business weather for Home."
            )

            weather_error = (
                "The latest weather could not be loaded. "
                "Please refresh the page later."
            )

    # Build all seven days, including days without records.
    chart_days = []

    for offset in range(7):
        sales_day = chart_start + timedelta(days=offset)

        chart_days.append({
            "date": sales_day,
            "amount": daily_amounts.get(sales_day, Decimal("0")),
            "has_records": sales_day in daily_amounts,
        })

    highest_amount = max(day["amount"] for day in chart_days)

    for day in chart_days:
        day["percentage"] = (
            round(day["amount"] / highest_amount * 100, 2)
            if highest_amount > 0
            else 0
        )

    # Rank this business's products by recorded monthly revenue.
    with get_db().cursor() as cursor:
        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.selling_unit,
                SUM(s.quantity_sold) AS quantity,
                SUM(s.sales_amount) AS revenue
            FROM daily_sales AS s
            JOIN products AS p ON p.product_id = s.product_id
            WHERE p.business_id = %s
              AND s.sale_date BETWEEN %s AND %s
            GROUP BY
                p.product_id,
                p.product_name,
                p.selling_unit
            HAVING SUM(s.sales_amount) > 0
            ORDER BY revenue DESC, p.product_name, p.product_id
            LIMIT 5
            """,
            (business["business_id"], month_start, today),
        )

        top_products = cursor.fetchall()

        # Use the same stock calculation as the Inventory page.
        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.selling_unit,
                COALESCE(
                    SUM(
                        CASE
                            WHEN m.movement_type IN (
                                'Stock In', 'Adjustment In'
                            )
                            THEN m.quantity
                            ELSE -m.quantity
                        END
                    ),
                    0
                ) AS available
            FROM products AS p
            LEFT JOIN stock_movements AS m
                ON m.product_id = p.product_id
            WHERE p.business_id = %s
            GROUP BY
                p.product_id,
                p.product_name,
                p.selling_unit
            HAVING available <= 0
            ORDER BY available, p.product_name
            """,
            (business["business_id"],),
        )

        stock_alerts = cursor.fetchall()

    return render_template(
        "business/dashboard.html",
        business=business,
        totals=totals,
        today=today,
        week_start=week_start,
        month_start=month_start,
        chart_days=chart_days,
        chart_start=chart_start,
        top_products=top_products,
        stock_alerts=stock_alerts,
        weather=weather,
        weather_error=weather_error,
    )

@app.route("/business/products/<int:product_id>/edit", methods=["GET", "POST"])
@business_required
def edit_product(product_id):
    database = get_db()
    error = None

    # Only retrieve a product belonging to the signed-in business.
    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.product_id, p.product_name,
                   p.selling_unit, p.selling_price
            FROM products AS p
            JOIN businesses AS b ON b.business_id = p.business_id
            WHERE p.product_id = %s AND b.user_id = %s
            """,
            (product_id, g.user["user_id"]),
        )
        product = cursor.fetchone()

    if product is None:
        abort(404)

    values = {
        "product_name": product["product_name"],
        "selling_price": str(product["selling_price"]),
    }

    if request.method == "POST":
        validate_csrf()

        values = {
            "product_name": request.form.get("product_name", "").strip(),
            "selling_price": request.form.get("selling_price", "").strip(),
        }

        price = None

        try:
            price = Decimal(values["selling_price"])

            if not price.is_finite():
                raise ValueError

            if price < 0 or price > Decimal("99999999.99"):
                raise ValueError

            if price != price.quantize(Decimal("0.01")):
                raise ValueError

        except (InvalidOperation, ValueError):
            error = (
                "Enter a price from 0 to 99,999,999.99 "
                "with no more than two decimal places."
            )

        if not 1 <= len(values["product_name"]) <= 100:
            error = "Enter a product name between 1 and 100 characters."

        if error is None:
            try:
                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE products AS p
                        JOIN businesses AS b
                            ON b.business_id = p.business_id
                        SET p.product_name = %s,
                            p.selling_price = %s
                        WHERE p.product_id = %s AND b.user_id = %s
                        """,
                        (
                            values["product_name"],
                            price,
                            product_id,
                            g.user["user_id"],
                        ),
                    )

                flash("Product updated successfully.", "product_success")
                return redirect(url_for("business_products"))

            except pymysql.err.IntegrityError as database_error:
                if database_error.args[0] == 1062:
                    error = "This product name already exists in your business."
                else:
                    app.logger.exception("Product update failed.")
                    error = "The product could not be updated."

            except pymysql.MySQLError:
                app.logger.exception("Database error updating a product.")
                error = "The product could not be updated. Please try again."

    return render_template(
        "business/edit_product.html",
        product=product,
        values=values,
        error=error,
    )

@app.route("/business/products", methods=["GET", "POST"])
@business_required
def business_products():
    database = get_db()
    error = None

    values = {
        "product_name": "",
        "selling_unit": "",
        "selling_price": "",
    }

    allowed_units = ("Piece", "Serving", "Pack", "Bottle")

    # Identify the business using the signed-in account.
    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT business_id, business_name, business_type, created_at
            FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

    if business is None:
        abort(403, description="Your account has no linked business.")

    if request.method == "POST":
        validate_csrf()

        values = {
            "product_name": request.form.get(
                "product_name", ""
            ).strip(),
            "selling_unit": request.form.get(
                "selling_unit", ""
            ).strip(),
            "selling_price": request.form.get(
                "selling_price", ""
            ).strip(),
        }

        price = None

        try:
            price = Decimal(values["selling_price"])

            if not price.is_finite():
                raise ValueError

            if price < 0 or price > Decimal("99999999.99"):
                raise ValueError

            if price != price.quantize(Decimal("0.01")):
                raise ValueError

        except (InvalidOperation, ValueError):
            error = (
                "Enter a price from 0 to 99,999,999.99 "
                "with no more than two decimal places."
            )

        if not 1 <= len(values["product_name"]) <= 100:
            error = "Enter a product name between 1 and 100 characters."

        elif values["selling_unit"] not in allowed_units:
            error = "Select a valid selling unit."

        if error is None:
            try:
                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO products (
                            business_id,
                            product_name,
                            selling_unit,
                            selling_price
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            business["business_id"],
                            values["product_name"],
                            values["selling_unit"],
                            price,
                        ),
                    )

                return redirect(url_for("business_products"))

            except pymysql.err.IntegrityError as database_error:
                if database_error.args[0] == 1062:
                    error = "This product name already exists in your business."
                else:
                    app.logger.exception("Product creation failed.")
                    error = "The product could not be saved."

            except pymysql.MySQLError:
                app.logger.exception("Database error while saving a product.")
                error = "The product could not be saved. Please try again."

    # Read the search text from the page URL.
    search = request.args.get("search", "").strip()[:100]

    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                product_id,
                product_name,
                selling_unit,
                selling_price
            FROM products
            WHERE business_id = %s
              AND LOCATE(%s, product_name) > 0
            ORDER BY product_name
            """,
            (business["business_id"], search),
        )

        products = cursor.fetchall()

    return render_template(
        "business/products.html",
        business=business,
        products=products,
        allowed_units=allowed_units,
        values=values,
        error=error,
        search=search,
    )

@app.route("/business/sales", methods=["GET", "POST"])
@business_required
def business_sales():
    database = get_db()
    error = None

    today = datetime.now(
        timezone(timedelta(hours=8))
    ).date()

    filters = {
        "start_date": request.args.get("start_date", "").strip(),
        "end_date": request.args.get("end_date", "").strip(),
        "search": request.args.get("search", "").strip()[:100],
    }

    start_date = None
    end_date = None
    filter_error = None

    try:
        if filters["start_date"]:
            start_date = date.fromisoformat(filters["start_date"])

        if filters["end_date"]:
            end_date = date.fromisoformat(filters["end_date"])

        if start_date and end_date and start_date > end_date:
            filter_error = "Start date must be on or before end date."

    except ValueError:
        filter_error = "Enter valid dates for the sales filter."

    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT business_id, business_name, business_type, created_at
            FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

        if business is None:
            abort(403, description="Your account has no linked business.")

        cursor.execute(
            """
            SELECT product_id, product_name, selling_unit, selling_price
            FROM products
            WHERE business_id = %s
            ORDER BY product_name
            """,
            (business["business_id"],),
        )

        products = cursor.fetchall()

    values = {
        "product_id": "",
        "sale_date": today.isoformat(),
        "quantity_sold": "",
        "sales_amount": "",
    }

    if request.method == "POST":
        validate_csrf()

        values = {
            field: request.form.get(field, "").strip()
            for field in values
        }

        # Only accept a product belonging to this business.
        selected_product = next(
            (
                product for product in products
                if str(product["product_id"]) == values["product_id"]
            ),
            None,
        )

        sale_date = None
        quantity = None
        amount = None

        try:
            sale_date = date.fromisoformat(values["sale_date"])

            if sale_date > today:
                error = "Actual sales cannot have a future date."

        except ValueError:
            error = "Enter a valid sales date."

        try:
            quantity = int(values["quantity_sold"])

            if quantity < 0 or quantity > 2147483647:
                raise ValueError

        except ValueError:
            error = "Enter a valid whole-number quantity of zero or more."

        if selected_product is None:
            error = "Choose one of your products."

        if error is None:
            # Calculate from the database price, not the submitted total.
            price = Decimal(str(selected_product["selling_price"]))
            amount = (price * quantity).quantize(Decimal("0.01"))

            if (
                not amount.is_finite()
                or amount < 0
                or amount > Decimal("9999999999.99")
            ):
                error = "The total is too large. Please check the quantity."
                values["sales_amount"] = ""
            else:
                values["sales_amount"] = format(amount, ".2f")

        if error is None:
            try:
                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO daily_sales (
                            product_id,
                            sale_date,
                            quantity_sold,
                            sales_amount
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            selected_product["product_id"],
                            sale_date,
                            quantity,
                            amount,
                        ),
                    )

                return redirect(url_for("business_sales"))

            except pymysql.err.IntegrityError as database_error:
                if database_error.args[0] == 1062:
                    error = (
                        "This product already has a sales record "
                        "for that date."
                    )
                else:
                    app.logger.exception("Sales record could not be saved.")
                    error = "The sales record could not be saved."

            except pymysql.MySQLError:
                app.logger.exception("Database error while saving sales.")
                error = "The sales record could not be saved. Try again."
    sales = []

    summary = {
        "total_sales": Decimal("0.00"),
        "record_count": 0,
    }

    if filter_error is None:
        with database.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(daily_sales.sales_amount), 0)
                        AS total_sales,
                    COUNT(*) AS record_count
                FROM daily_sales
                INNER JOIN products
                    ON products.product_id = daily_sales.product_id
                WHERE products.business_id = %s
                  AND (%s IS NULL OR daily_sales.sale_date >= %s)
                  AND (%s IS NULL OR daily_sales.sale_date <= %s)
                  AND LOCATE(%s, products.product_name) > 0
                """,
                (
                    business["business_id"],
                    start_date,
                    start_date,
                    end_date,
                    end_date,
                    filters["search"],
                ),
            )

            summary = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    daily_sales.sale_id,
                    daily_sales.sale_date,
                    daily_sales.quantity_sold,
                    daily_sales.sales_amount,
                    products.product_name,
                    products.selling_unit
                FROM daily_sales
                INNER JOIN products
                    ON products.product_id = daily_sales.product_id
                WHERE products.business_id = %s
                  AND (%s IS NULL OR daily_sales.sale_date >= %s)
                  AND (%s IS NULL OR daily_sales.sale_date <= %s)
                  AND LOCATE(%s, products.product_name) > 0
                ORDER BY
                    daily_sales.sale_date DESC,
                    daily_sales.sale_id DESC
                LIMIT 50
                """,
                (
                    business["business_id"],
                    start_date,
                    start_date,
                    end_date,
                    end_date,
                    filters["search"],
                ),
            )

            sales = cursor.fetchall()
    total_label = "Total for all dates"

    if filter_error is None:
        if start_date and end_date:
            if start_date == end_date:
                total_label = f"Total for {start_date.strftime('%b')} {start_date.day}, {start_date.year}"

            elif (
                start_date.year == end_date.year
                and start_date.month == end_date.month
            ):
                total_label = (
                    f"Total for {start_date.strftime('%b')} "
                    f"{start_date.day}–{end_date.day}, {end_date.year}"
                )

            elif start_date.year == end_date.year:
                total_label = (
                    f"Total for {start_date.strftime('%b')} {start_date.day}"
                    f" – {end_date.strftime('%b')} {end_date.day}, {end_date.year}"
                )

            else:
                total_label = (
                    f"Total for {start_date.strftime('%b')} {start_date.day}, {start_date.year}"
                    f" – {end_date.strftime('%b')} {end_date.day}, {end_date.year}"
                )

        elif start_date:
            total_label = (
                f"Total from {start_date.strftime('%b')} "
                f"{start_date.day}, {start_date.year} onward"
            )

        elif end_date:
            total_label = (
                f"Total through {end_date.strftime('%b')} "
                f"{end_date.day}, {end_date.year}"
            )

    return render_template(
        "business/sales.html",
        business=business,
        products=products,
        sales=sales,
        values=values,
        today=today.isoformat(),
        error=error,
        filters=filters,
        filter_error=filter_error,
        summary=summary,
        total_label=total_label,
    )

@app.route(
    "/business/sales/<int:sale_id>/edit",
    methods=["GET", "POST"],
)
@business_required
def edit_sale(sale_id):
    database = get_db()
    error = None

    today = datetime.now(
        timezone(timedelta(hours=8))
    ).date()

    # Find the record only if it belongs to the signed-in business.
    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                daily_sales.sale_id,
                daily_sales.sale_date,
                daily_sales.quantity_sold,
                daily_sales.sales_amount,
                products.product_name,
                products.selling_unit
            FROM daily_sales
            INNER JOIN products
                ON products.product_id = daily_sales.product_id
            INNER JOIN businesses
                ON businesses.business_id = products.business_id
            WHERE daily_sales.sale_id = %s
              AND businesses.user_id = %s
            """,
            (sale_id, g.user["user_id"]),
        )

        sale = cursor.fetchone()

    if sale is None:
        abort(404)

    values = {
        "sale_date": sale["sale_date"].isoformat(),
        "quantity_sold": str(sale["quantity_sold"]),
        "sales_amount": str(sale["sales_amount"]),
    }

    if request.method == "POST":
        validate_csrf()

        values = {
            field: request.form.get(field, "").strip()
            for field in values
        }

        sale_date = None
        quantity = None
        amount = None

        try:
            sale_date = date.fromisoformat(values["sale_date"])

            if sale_date > today:
                error = "Actual sales cannot have a future date."

        except ValueError:
            error = "Enter a valid sales date."

        try:
            quantity = int(values["quantity_sold"])

            if quantity < 0 or quantity > 2147483647:
                raise ValueError

        except ValueError:
            error = "Enter a valid whole-number quantity of zero or more."

        try:
            amount = Decimal(values["sales_amount"])

            if not amount.is_finite():
                raise ValueError

            if amount < 0 or amount > Decimal("9999999999.99"):
                raise ValueError

            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError

        except (InvalidOperation, ValueError):
            error = (
                "Enter a sales amount from 0 to 9,999,999,999.99 "
                "with no more than two decimal places."
            )

        if error is None and quantity == 0 and amount != 0:
            error = "Sales amount must be zero when quantity sold is zero."

        if error is None:
            try:
                with database.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE daily_sales
                        INNER JOIN products
                            ON products.product_id = daily_sales.product_id
                        INNER JOIN businesses
                            ON businesses.business_id = products.business_id
                        SET
                            daily_sales.sale_date = %s,
                            daily_sales.quantity_sold = %s,
                            daily_sales.sales_amount = %s
                        WHERE daily_sales.sale_id = %s
                          AND businesses.user_id = %s
                        """,
                        (
                            sale_date,
                            quantity,
                            amount,
                            sale_id,
                            g.user["user_id"],
                        ),
                    )

                return redirect(url_for("business_sales"))

            except pymysql.err.IntegrityError as database_error:
                if database_error.args[0] == 1062:
                    error = (
                        "This product already has a record "
                        "for the selected date."
                    )
                else:
                    app.logger.exception("Sales update failed.")
                    error = "The changes could not be saved."

            except pymysql.MySQLError:
                app.logger.exception("Database error while updating sales.")
                error = "The changes could not be saved. Try again."

    return render_template(
        "business/edit_sale.html",
        sale=sale,
        values=values,
        today=today.isoformat(),
        error=error,
    )

@app.route("/js/sidebar.js")
def sidebar_script():
    return send_from_directory(
        BASE_DIR / "js",
        "sidebar.js",
    )

@app.route("/js/theme.js")
def theme_script():
    return send_from_directory(
        BASE_DIR / "js",
        "theme.js",
    )

@app.route("/business/sales/export")
@business_required
def export_sales():
    start_text = request.args.get("start_date", "").strip()
    end_text = request.args.get("end_date", "").strip()

    start_date = None
    end_date = None

    try:
        if start_text:
            start_date = date.fromisoformat(start_text)

        if end_text:
            end_date = date.fromisoformat(end_text)

        if start_date and end_date and start_date > end_date:
            raise ValueError

    except ValueError:
        abort(
            400,
            description=(
                "Invalid date range. Return to Sales "
                "and correct the filters."
            ),
        )

    with get_db().cursor() as cursor:
        cursor.execute(
            """
            SELECT business_id
            FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

        if business is None:
            abort(403, description="Your account has no linked business.")

        cursor.execute(
            """
            SELECT
                daily_sales.sale_date,
                products.product_name,
                products.selling_unit,
                daily_sales.quantity_sold,
                daily_sales.sales_amount
            FROM daily_sales
            INNER JOIN products
                ON products.product_id = daily_sales.product_id
            WHERE products.business_id = %s
              AND (%s IS NULL OR daily_sales.sale_date >= %s)
              AND (%s IS NULL OR daily_sales.sale_date <= %s)
            ORDER BY
                daily_sales.sale_date DESC,
                daily_sales.sale_id DESC
            """,
            (
                business["business_id"],
                start_date,
                start_date,
                end_date,
                end_date,
            ),
        )

        sales = cursor.fetchall()

    def spreadsheet_text(value):
        text = str(value)

        # Prevent product names from being interpreted as formulas.
        if text.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + text

        if text.startswith(("\t", "\r", "\n")):
            return "'" + text

        return text

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Product",
        "Selling Unit",
        "Quantity Sold",
        "Sales Amount (PHP)",
    ])

    for sale in sales:
        writer.writerow([
            sale["sale_date"].isoformat(),
            spreadsheet_text(sale["product_name"]),
            spreadsheet_text(sale["selling_unit"]),
            sale["quantity_sold"],
            format(sale["sales_amount"], ".2f"),
        ])

    start_label = start_date.isoformat() if start_date else "beginning"
    end_label = end_date.isoformat() if end_date else "latest"

    filename = f"sales_{start_label}_to_{end_label}.csv"

    # UTF-8 BOM helps Excel recognize characters correctly.
    csv_content = output.getvalue().encode("utf-8-sig")
    output.close()

    return Response(
        csv_content,
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

@app.route("/business/inventory", methods=["GET", "POST"])
@business_required
def business_inventory():
    database = get_db()
    error = None

    movement_types = (
        "Stock In",
        "Sold",
        "Waste",
        "Adjustment In",
        "Adjustment Out",
    )

    outgoing_types = ("Sold", "Waste", "Adjustment Out")

    values = {
        "product_id": "",
        "movement_type": "",
        "quantity": "",
        "notes": "",
    }

    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT business_id, business_name, business_type, created_at
            FROM businesses
            WHERE user_id = %s
            """,
            (g.user["user_id"],),
        )

        business = cursor.fetchone()

    if business is None:
        abort(403, description="Your account has no linked business.")

    if request.method == "POST":
        validate_csrf()

        values = {
            field: request.form.get(field, "").strip()
            for field in values
        }

        product_id = None
        quantity = None

        try:
            product_id = int(values["product_id"])
            quantity = int(values["quantity"])

            if quantity < 1 or quantity > 2147483647:
                raise ValueError

        except ValueError:
            error = "Select a product and enter a positive whole quantity."

        if values["movement_type"] not in movement_types:
            error = "Select a valid movement type."

        if len(values["notes"]) > 255:
            error = "Notes cannot exceed 255 characters."

        if (
            values["movement_type"] in ("Adjustment In", "Adjustment Out")
            and not values["notes"]
        ):
            error = "Explain the reason for the stock adjustment."

        if error is None:
            try:
                database.begin()

                with database.cursor() as cursor:
                    # Lock this product while checking and changing its stock.
                    cursor.execute(
                        """
                        SELECT product_id
                        FROM products
                        WHERE product_id = %s
                          AND business_id = %s
                        FOR UPDATE
                        """,
                        (product_id, business["business_id"]),
                    )

                    product = cursor.fetchone()

                    if product is None:
                        error = "Select one of your business's products."

                    else:
                        cursor.execute(
                            """
                            SELECT COALESCE(
                                SUM(
                                    CASE
                                        WHEN movement_type IN (
                                            'Stock In', 'Adjustment In'
                                        )
                                        THEN quantity
                                        ELSE -quantity
                                    END
                                ),
                                0
                            ) AS available
                            FROM stock_movements
                            WHERE product_id = %s
                            """,
                            (product_id,),
                        )

                        available = cursor.fetchone()["available"]

                        if (
                            values["movement_type"] in outgoing_types
                            and quantity > available
                        ):
                            error = (
                                f"Only {available} units are available. "
                                "You cannot remove more than the available stock."
                            )

                        else:
                            cursor.execute(
                                """
                                INSERT INTO stock_movements (
                                    product_id,
                                    movement_type,
                                    quantity,
                                    notes
                                )
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    product_id,
                                    values["movement_type"],
                                    quantity,
                                    values["notes"],
                                ),
                            )

                if error:
                    database.rollback()
                else:
                    database.commit()
                    return redirect(url_for("business_inventory"))

            except pymysql.MySQLError:
                database.rollback()
                app.logger.exception("Stock movement could not be saved.")
                error = "The stock movement could not be saved. Try again."

    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                products.product_id,
                products.product_name,
                products.selling_unit,
                COALESCE(
                    SUM(
                        CASE
                            WHEN stock_movements.movement_type IN (
                                'Stock In', 'Adjustment In'
                            )
                            THEN stock_movements.quantity
                            ELSE -stock_movements.quantity
                        END
                    ),
                    0
                ) AS available
            FROM products
            LEFT JOIN stock_movements
                ON stock_movements.product_id = products.product_id
            WHERE products.business_id = %s
            GROUP BY
                products.product_id,
                products.product_name,
                products.selling_unit
            ORDER BY products.product_name
            """,
            (business["business_id"],),
        )

        products = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                stock_movements.created_at,
                stock_movements.movement_type,
                stock_movements.quantity,
                stock_movements.notes,
                products.product_name,
                products.selling_unit
            FROM stock_movements
            INNER JOIN products
                ON products.product_id = stock_movements.product_id
            WHERE products.business_id = %s
            ORDER BY stock_movements.movement_id DESC
            LIMIT 50
            """,
            (business["business_id"],),
        )

        movements = cursor.fetchall()

    return render_template(
        "business/inventory.html",
        business=business,
        products=products,
        movements=movements,
        movement_types=movement_types,
        values=values,
        error=error,
    )

from product_tools import install_product_tools

install_product_tools(
    app,
    get_db,
    business_required,
    validate_csrf,
)

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )