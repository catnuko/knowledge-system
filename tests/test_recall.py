"""FSRS 回取测试：到期队列、评分更新。"""
import json
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.growth.recall import due_cards, review  # noqa: E402


def test_due_and_review():
    con = db.connect()
    nid = db.insert_node(con, "claim", "回取测试", "这是一条需要间隔重复回取的知识笔记内容。", None)
    cards = due_cards(con)
    assert any(c["id"] == nid for c in cards)  # 新卡立即到期
    s1 = review(con, nid, "good")
    assert s1["reps"] == 1 and s1["state"] == 1  # learning
    assert "due" in s1 and s1["due"]
    # 到期检测必须对「今日到期」的卡返回（due 存的是带时区的 datetime，不能只按 date 字符串比较）
    due_today = due_cards(con)
    assert any(c["id"] == nid for c in due_today), "今日到期的卡必须出现在到期队列"
    node = db.get_node(con, nid)
    st = json.loads(node["recall_state"])
    assert st["reps"] == 1
    con.close()


def test_due_cards_today_with_datetime_due():
    """回归：recall_state.due 是带时间的 ISO datetime，到期检测不能只按 date 比较。"""
    from datetime import date
    con = db.connect()
    nid = db.insert_node(con, "claim", "到期边界", "验证 datetime 到期不会被漏掉的内容。", None)
    today = date.today().isoformat()
    db.update_recall_state(con, nid, {"due": f"{today}T02:04:33+00:00", "reps": 1})
    cards = due_cards(con)
    assert any(c["id"] == nid for c in cards), "due 为今日 datetime 的卡必须在到期队列"
    con.close()


def test_review_bad_rating():
    con = db.connect()
    nid = db.insert_node(con, "claim", "回取测试2", "另一条需要回取的知识笔记内容。", None)
    try:
        review(con, nid, "unknown")
        assert False, "应抛出 ValueError"
    except ValueError:
        pass
    con.close()
