"""Create an administrator without storing a password in command-line arguments."""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.auth.roles import RoleName  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.database.session import (  # noqa: E402
    create_database_engine,
    create_session_factory,
)
from app.schemas.user import UserCreate  # noqa: E402
from app.services.role_service import ensure_roles  # noqa: E402
from app.services.user_service import (  # noqa: E402
    DuplicateEmailError,
    create_user,
    get_user_by_email,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    engine = create_database_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            ensure_roles(session)
            existing = get_user_by_email(session, args.email)
            if existing is not None:
                session.commit()
                if existing.is_active and any(
                    role.name == RoleName.ADMIN for role in existing.roles
                ):
                    print("An active administrator with this email exists; unchanged.")
                    return 0
                print("Email already exists. No password, role or status was changed.")
                return 1
            password = os.environ.pop("FOOTLYTICS_ADMIN_PASSWORD", None)
            if password is None:
                if not sys.stdin.isatty():
                    print("Use an interactive terminal or FOOTLYTICS_ADMIN_PASSWORD.")
                    return 1
                password = getpass.getpass("Admin password (8–128 characters): ")
                if password != getpass.getpass("Confirm password: "):
                    print("Passwords do not match; no account created.")
                    return 1
            data = UserCreate(
                email=args.email,
                full_name=args.name,
                password=password,
                roles=[RoleName.ADMIN],
            )
            user = create_user(session, data)
            print(f"Administrator created: {user.email} (ID {user.id})")
            return 0
    except ValidationError as exc:
        # Never print ValidationError's raw input, which can contain the password.
        print("Invalid administrator details:")
        for error in exc.errors():
            print(f"  {'.'.join(str(part) for part in error['loc'])}: {error['msg']}")
        return 1
    except DuplicateEmailError:
        print("Email already exists; no account created.")
        return 1
    except OperationalError:
        print(
            "Cannot access auth tables. Check DATABASE_URL; run alembic upgrade head."
        )
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nAdministrator creation cancelled.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
