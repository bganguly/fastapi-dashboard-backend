from fastapi import APIRouter
from db import get_conn

router = APIRouter()


@router.get("/api/dataset-bounds")
def dataset_bounds():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT MIN("placedAt")::date AS "from", MAX("placedAt")::date AS "to" FROM orders'
            )
            row = cur.fetchone()
    return {
        "from": str(row[0]) if row and row[0] else "",
        "to":   str(row[1]) if row and row[1] else "",
    }
