"""Trusted local personal-link issuance; never an unauthenticated API endpoint."""

import argparse
import json
import os
from urllib.parse import quote
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from .candidate_service import issue_invitation
from .config import ROOT, settings
from .db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_id", type=UUID)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    try:
        with SessionLocal() as session:
            invitation, token = issue_invitation(session, args.application_id, args.days)
        directory = ROOT / "var/candidate-links"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / f"{invitation.id}.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(
                {
                    "application_id": str(args.application_id),
                    "invitation_id": str(invitation.id),
                    "expires_at": invitation.expires_at.isoformat(),
                    "token": token,
                    "personal_link": settings.web_origin.rstrip("/")
                    + "/interview#token="
                    + quote(token),
                },
                file,
                indent=2,
            )
        print(f"Personal-link details saved privately to {target}")
        print("Open personal_link in your browser, or use the token in Swagger Authorize.")
    except (ValueError, SQLAlchemyError, OSError):
        parser.exit(
            1,
            "Unable to issue/save personal link. Check the application, lifetime, database, and local storage.\n",
        )


if __name__ == "__main__":
    main()
