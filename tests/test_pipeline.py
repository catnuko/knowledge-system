"""加工流水线测试：去重、原子化、质量门。"""
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.ingest.pipeline import ingest_text  # noqa: E402


def test_ingest_dedup():
    con = db.connect()
    r1 = ingest_text(con, "这是第一条知识笔记，内容关于间隔重复算法的原理与实践应用。", kind="clipboard", title="t1")
    assert r1["added"] == 1
    r2 = ingest_text(con, "这是第一条知识笔记，内容关于间隔重复算法的原理与实践应用。", kind="clipboard", title="t1")
    assert r2["deduped"] is True and r2["added"] == 0
    con.close()


def test_ingest_quality_gate():
    con = db.connect()
    r = ingest_text(con, "太短了。\n\n" + "足够长的段落" * 10, kind="clipboard", title="t")
    assert r["added"] >= 1  # 长段进入，过短片段被质量门拦截
    con.close()
