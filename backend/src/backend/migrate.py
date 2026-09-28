from src.backend.db import initialize_database

if __name__ == "__main__":
    initialize_database()
    print("Database schema is up to date.")
