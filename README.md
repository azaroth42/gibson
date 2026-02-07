# GIBSON: Generative Interface for Biological / Synthetic Operative Networks

## Project Setup

This guide explains how to set up the Postgres database and run the Gibson application.

### Prerequisites

- **PostgreSQL**: Ensure PostgreSQL is installed and running on your machine.
- **Python 3.8+**: Ensure you have a compatible Python version installed.

### Installation

1. **Install Dependencies**
    It is recommended to use a virtual environment.

    ```bash
    pip install -r requirements.txt
    ```

### Database Setup

The application uses a PostgreSQL database named `gibson`.

#### 1. Create the Database

You need to create the database manually before running the initialization scripts.

```bash
createdb gibson
```

*Note: By default, the application connects to `localhost:5432` with user `postgres` and password `postgres` (or as configured in `db.py`). Set `DB_USER`, `DB_PASSWORD` etc. in your environment if different.*

#### 2. Initialize and Populate

Run the following scripts in order to generate the tables and populate them with the necessary data.

1. **Initialize Schema and Populate Cyberpunk Data**
    This script creates the tables (from `schema.sql` if needed) and populates the Cyberpunk 2020 ability tree and equipment.

    ```bash
    python populate_db.py
    ```

2. **Seed Dungeon World Items**
    Populates standard items from the Dungeon World rules.

    ```bash
    python seed_dw_items.py
    ```

3. **Seed Dungeon World Moves**
    Populates moves, classes, and character options from the Dungeon World rules.

    ```bash
    python seed_dw_moves.py
    ```

### Running the Application

Start the server using:

```bash
python main.py
```

Or with auto-reload enabled (for development):

```bash
hypercorn main:app --reload
```

The application will be available at `http://localhost:8000`.

DW Notes:

- Thaddeus needs to spend +3 Stat points
- Bodhi needs to spend 1 stat point, and level up
