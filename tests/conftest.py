from pathlib import Path

import pytest

from argo.db import DB


@pytest.fixture
def db(tmp_path: Path) -> DB:
    return DB(tmp_path / "test.db")
