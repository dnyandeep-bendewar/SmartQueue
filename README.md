# SmartQueue

SmartQueue is an AI-based queue waiting time prediction and management system. It is intended to help manage queues and provide estimated waiting times for visitors.

## Technology Stack

- Python
- Streamlit
- pandas
- NumPy
- scikit-learn
- Plotly
- joblib

## Main Features

- Queue management for visitors
- AI-based waiting time prediction
- Administration tools
- Queue analytics and visualizations

## Installation

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Apply the versioned schema before starting the application:

```powershell
python -m alembic upgrade head
```

For PostgreSQL, set `DATABASE_URL` in the environment before running Alembic.
When it is unset, Alembic uses the existing local SQLite database at
`database/smartqueue.db`.

For an existing SQLite database, do not run the initial migration against its
already-created tables. Back up the database, verify its schema matches the
initial revision, and then record the baseline without changing its tables or
data:

```powershell
python -m alembic stamp head
```

Do not stamp an older or unverified schema; it needs a dedicated migration
before the application can safely use it. After applying or stamping the
schema, start SmartQueue normally. An empty `admins` table still requires
`SMARTQUEUE_ADMIN_USERNAME` and `SMARTQUEUE_ADMIN_PASSWORD` for initial seeding.
