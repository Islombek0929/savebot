import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savebot.config import Config  # noqa: E402
from savebot.db import Database  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    return Config(
        bot_token="42:TEST",
        admin_ids=frozenset({1}),
        db_path=str(tmp_path / "bot.db"),
        tmp_dir=str(tmp_path / "tmp"),
        max_mb=50,
        max_parallel=2,
        per_user_limit=1,
        download_timeout=60,
    )


@pytest_asyncio.fixture
async def db(cfg):
    database = Database(cfg.db_path)
    await database.connect()
    yield database
    await database.close()
