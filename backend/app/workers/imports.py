import time

from sqlalchemy import select

from app.db.models import ImportBatch
from app.db.session import SessionLocal
from app.domain.imports import process_batch


def main() -> None:
    while True:
        with SessionLocal() as session:
            batch = session.scalar(
                select(ImportBatch)
                .where(ImportBatch.status == "pending")
                .order_by(ImportBatch.created_at)
                .limit(1)
            )
            if batch is not None:
                process_batch(session, batch)
                continue
        time.sleep(2)


if __name__ == "__main__":
    main()
