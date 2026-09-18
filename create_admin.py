from getpass import getpass

from werkzeug.security import generate_password_hash

from app import app, get_db


def create_admin():
    with app.app_context():
        database = get_db()

        with database.cursor() as cursor:
            cursor.execute(
                "SELECT user_id FROM users WHERE role = 'Admin'"
            )

            if cursor.fetchone():
                print("An admin account already exists.")
                return

            username = input("Admin username: ").strip()

            if not username or len(username) > 50:
                print("Use a username between 1 and 50 characters.")
                return

            cursor.execute(
                "SELECT user_id FROM users WHERE username = %s",
                (username,),
            )

            if cursor.fetchone():
                print("That username is already taken.")
                return

            password = getpass("Admin password: ")
            confirmation = getpass("Confirm password: ")

            if len(password) < 12:
                print("Use a password of at least 12 characters.")
                return

            if password != confirmation:
                print("Passwords do not match.")
                return

            password_hash = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO users (
                    username,
                    password_hash,
                    role
                )
                VALUES (%s, %s, 'Admin')
                """,
                (username, password_hash),
            )

        print("Admin account created successfully.")


if __name__ == "__main__":
    create_admin()