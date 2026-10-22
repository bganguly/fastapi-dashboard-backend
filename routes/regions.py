from fastapi import APIRouter
from db import get_conn

router = APIRouter()


@router.get("/api/regions")
def list_regions():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, code, name FROM regions ORDER BY code")
            rows = cur.fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2]} for r in rows]
