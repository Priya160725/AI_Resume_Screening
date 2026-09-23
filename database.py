import os
import mysql.connector
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


# ==========================================================
# MYSQL CONNECTION
# ==========================================================

def get_connection():

    connection = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )

    return connection


# ==========================================================
# TEST CONNECTION
# ==========================================================

if __name__ == "__main__":

    try:

        connection = get_connection()

        print("MySQL connection successful!")

        connection.close()

    except mysql.connector.Error as error:

        print("MySQL connection failed.")
        print(error)