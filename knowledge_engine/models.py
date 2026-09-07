"""领域模型：节点、边、来源、FSRS 记忆状态。"""
from pydantic import BaseModel, Field

NODE_TYPES = ("concept", "claim", "question")
REL_TYPES = (
    "implies",          # 蕴含 / 因果
    "supports",         # 支持 / 证据
    "contradicts",      # 反对 / 矛盾
    "exemplifies",      # 实例 / 例证
    "refines",          # 细化 / 精化
    "prerequisite_of",  # 前提 / 先决（KST）
    "contrasts",        # 对比 / 区分
    "merges",           # 同义合并
    "relates",          # 弱关联（必须人工确认）
)
NODE_STATUS = ("draft", "active", "archived", "pending_link")
CONFIRM_STATUS = ("auto", "pending", "approved", "rejected")
SOURCE_KINDS = ("url", "clipboard", "message", "file", "audio", "handwritten", "synthesis")


class RecallState(BaseModel):
    """FSRS 卡片状态（对齐 fsrs.Card 的关键字段）。"""
    difficulty: float = 0.0
    stability: float = 0.0
    due: str = ""          # ISO 日期
    reps: int = 0
    lapses: int = 0
    state: int = 0         # 0=new 1=learning 2=review 3=relearning


class Source(BaseModel):
    id: int | None = None
    kind: str = Field(pattern="|".join(SOURCE_KINDS))
    raw_path: str = ""
    text_extracted: str = ""
    fingerprint: str = ""
    title: str = ""
    captured_at: str = ""


class Node(BaseModel):
    id: int | None = None
    type: str = Field(pattern="|".join(NODE_TYPES))
    title: str
    body: str
    source_ref: int | None = None
    status: str = Field(default="active", pattern="|".join(NODE_STATUS))
    recall_state: RecallState = RecallState()
    created_at: str = ""
    updated_at: str = ""


class Edge(BaseModel):
    id: int | None = None
    src_id: int
    dst_id: int
    rel_type: str = Field(pattern="|".join(REL_TYPES))
    rationale: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    confirm_status: str = Field(default="pending", pattern="|".join(CONFIRM_STATUS))
    created_at: str = ""
