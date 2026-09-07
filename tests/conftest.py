import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _fresh_db():
    os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")
    yield
