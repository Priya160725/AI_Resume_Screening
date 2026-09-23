import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )


if __name__ == "__main__":
    try:
        connection = get_connection()
        print("MYSQL CONNECTION SUCCESS")
        connection.close()
    except mysql.connector.Error as error:
        print("MYSQL CONNECTION FAILED")
        print(error)