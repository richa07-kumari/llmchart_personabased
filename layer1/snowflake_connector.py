import os
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


class SnowflakeConnector:

    def __init__(self):
        self.conn = None
        self.warehouse = os.getenv("SNOWFLAKE_WAREHOUSE")
        self.database = os.getenv("SNOWFLAKE_DATABASE")
        self.schema = os.getenv("SNOWFLAKE_SCHEMA")

    def connect(self):
        """
        Create Snowflake connection
        """

        self.conn = snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse=self.warehouse,
            database=self.database,
            schema=self.schema,
            role=os.getenv("SNOWFLAKE_ROLE")
        )

        print("Connected to Snowflake")

    def execute_query(self, query):
        """
        Execute SQL query and return results
        """

        if self.conn is None:
            self.connect()

        cursor = self.conn.cursor(snowflake.connector.DictCursor)

        try:
            cursor.execute(query)
            result = cursor.fetchall()
            return result

        finally:
            cursor.close()

    def test_connection(self):
        """
        Test Snowflake connection
        """

        try:
            result = self.execute_query(
                "SELECT CURRENT_VERSION() AS version"
            )

            print("Connection Successful")
            print("Snowflake Version:", result[0]["VERSION"])
            return True

        except Exception as e:
            print("Connection Failed")
            print(e)
            return False

    def close(self):
        """
        Close Snowflake connection
        """

        if self.conn:
            self.conn.close()
            print("Connection Closed")
