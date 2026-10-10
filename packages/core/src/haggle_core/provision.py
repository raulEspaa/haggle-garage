"""Create one Postgres role per service with least privilege (docs/03-contracts.md §5.3).

    uv run haggle-provision-roles --admin-url "$NEON_DATABASE_URL" --to-secret-manager PROJECT
    uv run haggle-provision-roles --admin-url <local url> --print   # local testing only

Each run sets a NEW random password per role (rotation for free). With --to-secret-manager the
connection strings go straight from this process to Secret Manager through `gcloud` on stdin:
they are never printed, written to disk or put in the Terraform state.

The point of separate roles: a bug or a prompt injection in one service can only do what that
service's role allows. The seller's role cannot read `games.floor_usd` AT ALL; the view
`seller_game_context` is its only window on a game, and it hides the floor at level 3.
"""

import argparse
import secrets
import subprocess
import sys

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import URL

# Column lists: Postgres checks privileges per column for UPDATE ... SET and for every column
# read in WHERE / RETURNING. SELECT ... FOR UPDATE needs UPDATE on at least one column.
GRANTS: dict[str, list[str]] = {
    "haggle_api": [
        "GRANT SELECT ON cars, pricing_policies, turns, deals, llm_usage TO {role}",
        "GRANT SELECT, INSERT ON games TO {role}",
        "GRANT UPDATE (status, ended_at, floor_guess_usd, floor_guess_correct) ON games TO {role}",
        "GRANT INSERT ON turns TO {role}",  # the templated greeting (turn 0)
    ],
    "haggle_seller": [
        "GRANT SELECT ON seller_game_context TO {role}",
        "GRANT SELECT (id, status, turn_count, turn_cap, model_id) ON games TO {role}",
        "GRANT UPDATE (turn_count, last_activity_at, status, ended_at, model_id, prompt_version)"
        " ON games TO {role}",
        "GRANT SELECT, INSERT ON turns, llm_usage TO {role}",
        # ADK keeps its sessions in schema `adk` and creates its own tables there. They may
        # already exist, created by another role (found testing these grants locally).
        "GRANT USAGE, CREATE ON SCHEMA adk TO {role}",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA adk TO {role}",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA adk TO {role}",
    ],
    "haggle_mcp": [
        "GRANT SELECT ON games, cars, pricing_policies, model_sheets, sheet_chunks,"
        " negotiation_events, deals TO {role}",
        "GRANT INSERT ON negotiation_events, deals TO {role}",
        "GRANT UPDATE (status, final_price_usd, ended_at) ON games TO {role}",
    ],
}
SECRET_NAMES = {
    "haggle_api": "haggle-db-url-api",
    "haggle_seller": "haggle-db-url-seller",
    "haggle_mcp": "haggle-db-url-mcp",
}


def service_url(admin_url: URL, role: str, password: str) -> str:
    url = admin_url.set(drivername="postgresql+psycopg", username=role, password=password)
    return url.render_as_string(hide_password=False)


def provision(admin_url: str) -> dict[str, str]:
    """Create or rotate the roles and apply the grants. Returns role -> connection string."""
    parsed = make_url(admin_url).set(drivername="postgresql+psycopg")
    engine = create_engine(parsed)
    urls: dict[str, str] = {}
    with engine.begin() as conn:
        conn.execute(text("GRANT USAGE ON SCHEMA public TO PUBLIC"))
        for role, grants in GRANTS.items():
            password = secrets.token_urlsafe(32)
            exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
            verb = "ALTER" if exists else "CREATE"
            # Identifiers can't be bound parameters; role names are constants from this file and
            # the password is URL-safe base64, so the f-string cannot be injected into.
            conn.execute(text(f"{verb} ROLE {role} LOGIN PASSWORD '{password}'"))
            conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}"))
            for grant in grants:
                conn.execute(text(grant.format(role=role)))
            urls[role] = service_url(parsed, role, password)
    engine.dispose()
    return urls


def _to_secret_manager(urls: dict[str, str], project: str) -> None:
    for role, url in urls.items():
        subprocess.run(  # noqa: S603 (fixed command; the secret travels on stdin, not argv)
            [  # noqa: S607
                "gcloud",
                "secrets",
                "versions",
                "add",
                SECRET_NAMES[role],
                f"--project={project}",
                "--data-file=-",
            ],
            input=url.encode(),
            check=True,
            capture_output=True,
        )
        print(f"{role}: new password stored in secret {SECRET_NAMES[role]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--admin-url", required=True, help="Owner connection string")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--to-secret-manager", metavar="PROJECT_ID")
    target.add_argument("--print", action="store_true", help="local databases only")
    args = parser.parse_args()
    if args.print and (make_url(args.admin_url).host or "") not in ("localhost", "127.0.0.1", "db"):
        sys.exit("--print is only allowed for local databases: use --to-secret-manager")
    urls = provision(args.admin_url)
    if args.print:
        for role, url in urls.items():
            print(f"{role}={url}")
    else:
        _to_secret_manager(urls, args.to_secret_manager)
