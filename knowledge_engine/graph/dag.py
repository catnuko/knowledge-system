"""前提 DAG（KST）：环检测与可达性查询。"""
from .. import db


def path_exists(con, start: int, target: int) -> bool:
    """是否存在 start →…→ target 的 prerequisite_of 路径（递归 CTE）。"""
    row = con.execute(
        """
        WITH RECURSIVE reach(x) AS (
            SELECT dst_id FROM edges WHERE src_id = ? AND rel_type = 'prerequisite_of'
                AND confirm_status != 'rejected'
            UNION
            SELECT e.dst_id FROM edges e JOIN reach r ON e.src_id = r.x
                WHERE e.rel_type = 'prerequisite_of' AND e.confirm_status != 'rejected'
        )
        SELECT EXISTS(SELECT 1 FROM reach WHERE x = ?) AS hit
        """,
        (start, target),
    ).fetchone()
    return bool(row and row["hit"])


def creates_cycle(con, src: int, dst: int) -> bool:
    """若新增 src→dst（prerequisite_of）会造成环，返回 True。"""
    return path_exists(con, dst, src)
