import os
import tempfile
from pathlib import Path

os.environ["BOT_TOKEN"] = "123456:TESTTOKEN_FOR_UNIT_TESTS_ONLY"
os.environ["RAPID_API_KEY"] = "test-rapidapi-key"

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_PATH"] = _db_file.name
_db_file.close()

import pytest

from models import create_models, db, SearchHistory, User
import api
import main


@pytest.fixture(autouse=True)
def _reset_state(tmp_path):
    main.user_states.clear()
    main.city_limiter = main.RateLimiter(max_calls=5, window_sec=60)
    main.hotel_limiter = main.RateLimiter(max_calls=3, window_sec=60)
    api._url_cache = api.TtlCache(ttl_sec=3600, max_size=512)
    yield


@pytest.fixture
def app_db():
    create_models()
    if not db.is_closed():
        SearchHistory.delete().execute()
        User.delete().execute()
    yield db
