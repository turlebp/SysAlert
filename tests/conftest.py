# tests/conftest.py
"""
Pytest configuration and fixtures.
"""
import pytest
import sys
from pathlib import Path
import tempfile

# Add parent directory to Python path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import DB


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DB(db_url=f"sqlite:///{db_path}")
        yield db


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "min_interval_seconds": 20,
        "max_concurrent_checks": 50,
        "connection_timeout": 5,
        "cpu_benchmark": {
            "enabled": False,
            "url": "",
            "threshold_seconds": 0.35,
            "poll_interval_seconds": 300
        }
    }