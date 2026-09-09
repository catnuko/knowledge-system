"""FSRS 间隔重复回取：到期队列 + 评分更新（fsrs >= 6.x 新 API）。"""
import json
from datetime import datetime

from .. import db

RATINGS = {"again": 1, "hard": 2, "good": 3, "easy": 4}
_CARD_FIELDS = ("card_id", "state", "step", "stability", "difficulty", "due", "last_review")


def due_cards(con, limit: int = 20) -> list[dict]:
    """到期卡片：新卡（无状态）或 due <= 今天。返回 [{id,title,body,recall_state}]。"""
    rows = con.execute(
        """SELECT id, title, body, recall_state FROM nodes
           WHERE status = 'active'
             AND (recall_state = '{}'
                  OR json_extract(recall_state, '$.due') IS NULL
                  OR date(json_extract(recall_state, '$.due')) <= date('now'))
           ORDER BY id LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def review(con, nid: int, rating: str) -> dict:
    """回取评分：again/hard/good/easy。返回更新后的记忆状态。"""
    from fsrs import Card, Rating, Scheduler

    node = db.get_node(con, nid)
    if node is None:
        raise KeyError(nid)
    raw = json.loads(node["recall_state"] or "{}")

    card = _card_from_state(raw) if raw else Card()
    sched = Scheduler()
    rating_key = rating.strip().lower()
    if rating_key not in RATINGS:
        raise ValueError(f"评分必须是 again/hard/good/easy，收到: {rating}")
    new_card, _log = sched.review_card(card, Rating(RATINGS[rating_key]))

    reps = int(raw.get("reps", 0)) + 1
    lapses = int(raw.get("lapses", 0)) + (1 if rating_key == "again" else 0)
    state = {
        "card_id": str(new_card.card_id),
        "state": int(new_card.state.value),
        "step": new_card.step,
        "stability": round(new_card.stability, 4),
        "difficulty": round(new_card.difficulty, 4),
        "due": new_card.due.isoformat(),
        "last_review": new_card.last_review.isoformat() if new_card.last_review else "",
        "reps": reps,
        "lapses": lapses,
    }
    db.update_recall_state(con, nid, state)
    return state


def _card_from_state(raw: dict):
    from fsrs import Card

    from datetime import timezone

    keep = {k: v for k, v in raw.items() if k in _CARD_FIELDS and v is not None}
    for key in ("due", "last_review"):
        if keep.get(key):
            keep[key] = datetime.fromisoformat(keep[key])
            if keep[key].tzinfo is None:
                keep[key] = keep[key].replace(tzinfo=timezone.utc)
    try:
        return Card(**keep)
    except TypeError:
        return Card()
