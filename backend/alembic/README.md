# Database migrations

From backend/, run `python -m alembic upgrade head`. The URL comes from centralized
settings and the root .env. Revision 0001_users_and_roles creates users, roles,
user_roles and the five required roles. Repeating upgrade head is a no-op.

`python -m alembic check` detects drift between models and migrations. Generate
future revisions with `python -m alembic revision --autogenerate -m "description"`
and review the result before applying it. Use SQLite batch migrations when needed.
API startup never creates tables. Downgrading to base destroys the auth tables;
exercise that command only on disposable databases unless data loss is intended.
