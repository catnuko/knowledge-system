#!/usr/bin/env python3
"""knowledge-engine CLI。

用法示例：
  ke ingest-text "一段笔记文本"
  ke ingest-file notes.md
  ke ingest-url https://example.com/article
  ke link --all
  ke recall
  ke review 3 good
  ke stats
  ke conflicts
  ke synthesize
  ke serve --port 8000
"""
import argparse
import json
import sys

from knowledge_engine import db
from knowledge_engine.config import Config
from knowledge_engine.llm.base import get_provider


def _con(cfg):
    return db.connect(cfg)


def cmd_ingest_text(args, cfg):
    con = _con(cfg)
    r = _ingest(con, args.text, "clipboard", args.title, "", cfg)
    _print_ingest(r)
    con.close()


def cmd_ingest_file(args, cfg):
    from knowledge_engine.ingest.pipeline import ingest_file
    con = _con(cfg)
    r = ingest_file(con, args.path, cfg=cfg)
    _print_ingest(r)
    con.close()


def cmd_ingest_url(args, cfg):
    from knowledge_engine.ingest.pipeline import ingest_url
    con = _con(cfg)
    r = ingest_url(con, args.url, cfg=cfg)
    _print_ingest(r)
    con.close()


def _ingest(con, text, kind, title, raw, cfg):
    from knowledge_engine.ingest.pipeline import ingest_text
    return ingest_text(con, text, kind=kind, title=title, raw_path=raw, cfg=cfg)


def _print_ingest(r):
    if r.get("deduped"):
        print(f"去重命中：来源 #{r['source_id']}，跳过。")
    else:
        print(f"来源 #{r['source_id']}：新增 {r['added']} 节点（跳过 {r['skipped']} 条质量门），节点 {r['node_ids']}")


def cmd_link(args, cfg):
    from knowledge_engine.graph.linker import link_all_pending, mark_orphans, link_node
    con = _con(cfg)
    provider = get_provider(cfg)
    if args.node:
        s = link_node(con, args.node, provider, cfg)
        print(f"节点 {args.node}：自动建链 {s['linked']}，待确认 {s['pending']}，环拦截 {s['cycles']}")
    else:
        s = link_all_pending(con, provider, cfg, limit=args.limit)
        print(f"全部未链接节点：自动建链 {s['linked']}，待确认 {s['pending']}，环拦截 {s['cycles']}")
    o = mark_orphans(con, cfg)
    if o:
        print(f"孤儿标记 pending_link：{o}")
    con.close()


def cmd_recall(args, cfg):
    from knowledge_engine.growth.recall import due_cards, review
    con = _con(cfg)
    cards = due_cards(con, limit=args.limit)
    if not cards:
        print("今日无到期卡片。")
    else:
        print(f"今日到期 {len(cards)} 张：")
        for c in cards:
            state = c["recall_state"]
            tag = "新卡" if state in ("{}", "") else f"复习#{json.loads(state).get('reps', 0)}"
            print(f"  [{c['id']}] ({tag}) {c['title']}")
    con.close()


def cmd_review(args, cfg):
    from knowledge_engine.growth.recall import review
    con = _con(cfg)
    try:
        state = review(con, args.node, args.rating)
    except (KeyError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    print(f"节点 {args.node} 已更新：{json.dumps(state, ensure_ascii=False)}")
    con.close()


def cmd_stats(args, cfg):
    from knowledge_engine.growth.metrics import all_metrics
    con = _con(cfg)
    print(json.dumps(all_metrics(con), ensure_ascii=False, indent=2))
    con.close()


def cmd_conflicts(args, cfg):
    from knowledge_engine.growth.conflict import conflicts
    con = _con(cfg)
    items = conflicts(con)
    if not items:
        print("当前无未解决的矛盾。")
    for c in items:
        print(f"[边 {c['edge_id']}] {c['a']['title']}  ↔  {c['b']['title']}（置信 {c['confidence']}）")
        print(f"  理由：{c['rationale']}")
    con.close()


def cmd_synthesize(args, cfg):
    from knowledge_engine.growth.synthesize import weekly_synthesis
    con = _con(cfg)
    provider = get_provider(cfg)
    r = weekly_synthesis(con, provider)
    for it in r.get("items", []):
        print(f"综合产出 #{it['node_id']}：{it['topic']}（基于 {it['size']} 节点）")
    if not r.get("items"):
        print("暂无足够节点进行综合（需要 ≥2 节点的连通分量）。")
    con.close()


def cmd_serve(args, cfg):
    import uvicorn
    from knowledge_engine.web.app import create_app
    app = create_app(cfg)
    print(f"knowledge-engine 面板：http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ke", description="个人知识系统 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ingest-text", help="从剪贴板/文本采集")
    sp.add_argument("text")
    sp.add_argument("--title", default="")
    sp.set_defaults(fn=cmd_ingest_text)

    sp = sub.add_parser("ingest-file", help="从本地文件采集")
    sp.add_argument("path")
    sp.set_defaults(fn=cmd_ingest_file)

    sp = sub.add_parser("ingest-url", help="从链接提取网页采集")
    sp.add_argument("url")
    sp.set_defaults(fn=cmd_ingest_url)

    sp = sub.add_parser("link", help="建链（自动 + 待确认 + 孤儿标记）")
    sp.add_argument("--node", type=int, default=None)
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--all", action="store_true", help="处理全部未链接节点")
    sp.set_defaults(fn=cmd_link)

    sp = sub.add_parser("recall", help="列出今日到期回取卡片")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_recall)

    sp = sub.add_parser("review", help="回取评分：again/hard/good/easy")
    sp.add_argument("node", type=int)
    sp.add_argument("rating", choices=["again", "hard", "good", "easy"])
    sp.set_defaults(fn=cmd_review)

    sp = sub.add_parser("stats", help="指标面板")
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("conflicts", help="矛盾检测报告")
    sp.set_defaults(fn=cmd_conflicts)

    sp = sub.add_parser("synthesize", help="每周综合")
    sp.set_defaults(fn=cmd_synthesize)

    sp = sub.add_parser("serve", help="启动 Web 面板")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    cfg = Config()
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
