from collections import defaultdict
from fastapi import APIRouter, Query
from db import get_conn

router = APIRouter()

@router.get("/api/aggregates")
def get_aggregates(
    from_: str = Query(alias="from"),
    to: str = Query(),
    topCategories: int = Query(default=5, ge=1, le=20),
    includeData: bool = True,
    includeTotal: bool = True,
):
    result: dict = {}

    if includeData:
        rows = _query_daily_summary(from_, to)
        result["data"] = _build_result(rows, topCategories)

    if includeTotal:
        count_sql = """
            SELECT COUNT(DISTINCT id) FROM orders
            WHERE "placedAt"::date BETWEEN %s::date AND %s::date
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, [from_, to])
                result["totalOrders"] = cur.fetchone()[0]
        result["totalOrdersApproximate"] = False

    return result


def _query_daily_summary(from_: str, to: str) -> list:
    sql = """
        SELECT date::text AS day, "categoryName" AS category,
               SUM("totalOrders")  AS total_orders,
               SUM("totalRevenue") AS total_revenue,
               SUM("totalItems")   AS total_items
        FROM daily_summary
        WHERE date BETWEEN %s::date AND %s::date
        GROUP BY date, "categoryName"
        ORDER BY date
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [from_, to])
            return cur.fetchall()


def _build_result(rows: list, top_n: int) -> list:
    by_day: dict[str, dict] = {}
    day_order: list[str] = []

    for day, cat, total_orders, total_revenue, total_items in rows:
        if day not in by_day:
            by_day[day] = {}
            day_order.append(day)
        by_day[day][cat] = {
            "totalOrders": int(total_orders or 0),
            "totalRevenue": float(total_revenue or 0),
            "totalItems": int(total_items or 0),
        }

    cat_totals: dict[str, int] = defaultdict(int)
    for day_cats in by_day.values():
        for cat, vals in day_cats.items():
            cat_totals[cat] += vals["totalOrders"]

    top_cats = {
        k for k, _ in sorted(cat_totals.items(), key=lambda x: -x[1])[:top_n]
    }

    result = []
    for day in day_order:
        cats: dict = {}
        others_orders = 0
        others_revenue = 0.0
        others_items = 0

        for cat, vals in by_day[day].items():
            o, r, i = vals["totalOrders"], vals["totalRevenue"], vals["totalItems"]
            if cat in top_cats:
                cats[cat] = {
                    "totalOrders": o,
                    "totalRevenue": r,
                    "totalItems": i,
                    "avgOrderValue": r / o if o > 0 else 0.0,
                }
            else:
                others_orders += o
                others_revenue += r
                others_items += i

        if others_orders > 0:
            cats["Others"] = {
                "totalOrders": others_orders,
                "totalRevenue": others_revenue,
                "totalItems": others_items,
                "avgOrderValue": others_revenue / others_orders,
            }

        result.append({"date": day, "categories": cats})

    return result
