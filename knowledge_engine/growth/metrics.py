"""指标面板：结构 / 行为 / 产出。"""
from .. import db


def all_metrics(con) -> dict:
    s = db.stats(con)
    due = con.execute(
        """SELECT COUNT(*) c FROM nodes WHERE status='active'
           AND (recall_state='{}' OR json_extract(recall_state,'$.due') IS NULL
                OR date(json_extract(recall_state,'$.due')) <= date('now'))""").fetchone()["c"]
    reviewed = con.execute(
        "SELECT COUNT(*) c FROM nodes WHERE recall_state != '{}'").fetchone()["c"]
    synthesis = con.execute(
        "SELECT COUNT(*) c FROM nodes WHERE source_ref IN (SELECT id FROM sources WHERE kind='synthesis')").fetchone()["c"]
    pending = con.execute(
        "SELECT COUNT(*) c FROM edges WHERE confirm_status='pending'").fetchone()["c"]
    recalled = con.execute(
        """SELECT COUNT(*) c FROM nodes WHERE recall_state != '{}'
           AND json_extract(recall_state,'$.reps') >= 1""").fetchone()["c"]
    mastery = db.all_mastery(con)
    feynman_total = con.execute(
        "SELECT COUNT(*) c FROM verifications WHERE mode='feynman'").fetchone()["c"]
    return {
        **s,
        "due_today": due,
        "reviewed": reviewed,
        "recalled_nodes": recalled,
        "pending_edges": pending,
        "synthesis_count": synthesis,
        "mastery_avg": mastery["avg"],
        "mastery_verified": mastery["verified"],
        "feynman_count": feynman_total,
    }
