"""pytest 全局 fixture：每个测试使用独立临时数据库。"""
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _fresh_db():
    os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")
    yield
