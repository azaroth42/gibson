# Gibson Project Setup

This guide explains how to set up the Postgres database and run the Gibson application.

## Prerequisites

- **PostgreSQL**: Ensure PostgreSQL is installed and running on your machine.
- **Python 3.8+**: Ensure you have a compatible Python version installed.

## Installation

1.  **Install Dependencies**
    It is recommended to use a virtual environment.
    ```bash
    pip install -r requirements.txt
    ```

## Database Setup

The application uses a PostgreSQL database named `gibson`.

### 1. Create the Database

You need to create the database manually before running the initialization scripts.

```bash
# Command line example (or use a GUI tool like PgAdmin/TablePlus)
createdb gibson
```

*Note: By default, the application connects to `localhost:5432` with user `postgres` and password `postgres`. If your configuration differs, set the following environment variables:*
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`

### 2. Initialize the Database

Run the following scripts in order to generate the tables and populate them with the necessary data.

1.  **Create Schema (Tables)**
    This script drops existing tables and recreates the database schema.
    ```bash
    python reset_db.py
    ```

2.  **Populate Ability Tree**
    This script parses `advances.md` and populates the `ability_nodes` table.
    ```bash
    python rebuild_tree.py
    ```

3.  **Populate Equipment**
    This script parses `equipment.md` and populates the `items` table.
    ```bash
    python import_equipment.py
    ```

### 3. Verify Setup (Optional)

You can run the test character creation script to ensure everything is working correctly.
```bash
python create_test_char.py
```

## Running the Application

Start the server using:
```bash
python main.py
```
Or with auto-reload enabled (for development):
```bash
hypercorn main:app --reload
```

The application will be available at `http://localhost:8000`.
