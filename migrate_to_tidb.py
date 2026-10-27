import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=True)


def get_connection(prefix):
    if prefix == "LOCAL_DB_":
        return mysql.connector.connect(
            host=os.getenv("LOCAL_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("LOCAL_DB_PORT", "3306")),
            user=os.getenv("LOCAL_DB_USER", "root"),
            password=os.getenv("LOCAL_DB_PASSWORD"),
            database=os.getenv("LOCAL_DB_NAME", "inventory_db"),
            connection_timeout=10,
            use_pure=True,
        )

    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "4000")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca=os.getenv("DB_SSL_CA", "certs/tidb-ca.pem"),
        ssl_verify_cert=True,
        connection_timeout=15,
        use_pure=True,
    )
TABLES = ["users", "products", "sales", "stock_movements"]

def main():
    source = None
    target = None

    try:
        source = get_connection("LOCAL_DB_")
        target = get_connection("DB_")

        source_cursor = source.cursor(dictionary=True)
        target_cursor = target.cursor()

        # Safety check: never insert into a non-empty destination.
        for table in TABLES:
            target_cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            count = target_cursor.fetchone()[0]

            if count != 0:
                raise RuntimeError(
                    f"TiDB table '{table}' contains {count} rows. "
                    "Migration stopped to prevent duplicates."
                )

        # Copy parent tables before dependent tables.
        for table in TABLES:
            source_cursor.execute(f"SELECT * FROM `{table}`")
            rows = source_cursor.fetchall()

            if not rows:
                print(f"{table}: 0 rows")
                continue

            columns = list(rows[0].keys())
            column_sql = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))

            insert_sql = (
                f"INSERT INTO `{table}` ({column_sql}) "
                f"VALUES ({placeholders})"
            )

            values = [
                tuple(row[column] for column in columns)
                for row in rows
            ]

            target_cursor.executemany(insert_sql, values)
            print(f"{table}: copied {len(rows)} rows")

        target.commit()

        print("\nMigration completed successfully.")

        # Verify destination counts.
        for table in TABLES:
            target_cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            print(f"TiDB {table}: {target_cursor.fetchone()[0]} rows")

        source_cursor.close()
        target_cursor.close()

    except Exception as error:
        if target is not None:
            target.rollback()

        print(f"\nMigration failed: {error}")
        print("The migration transaction was rolled back where supported.")

    finally:
        if source is not None and source.is_connected():
            source.close()
        if target is not None and target.is_connected():
            target.close()


if __name__ == "__main__":
    main()
