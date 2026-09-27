from pathlib import Path

import pytest

from realestate import db

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "Abc+/Def==Secret/Key+123=="


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", FAKE_KEY)
    return FAKE_KEY
