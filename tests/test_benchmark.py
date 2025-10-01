"""
Test CPU benchmark parsing functionality.
"""
import pytest
from benchmark import _parse_possible_structures


def test_parse_list_of_dicts():
    """Test parsing list of dictionaries format."""
    data = [
        {"name": "turtlebp", "data": [[1600000000, 0.3], [1600000100, 0.4]]},
        {"name": "other", "data": [[1600000000, 0.2]]}
    ]
    
    result = _parse_possible_structures(data, "turtlebp")
    assert result is not None
    ts, val = result
    assert ts == 1600000100
    assert val == 0.4


def test_parse_dict_of_lists():
    """Test parsing dictionary format."""
    data = {
        "turtlebp": [[1600000000, 0.2], [1600000200, 0.25]],
        "other": [[1600000000, 0.3]]
    }
    
    result = _parse_possible_structures(data, "turtlebp")
    assert result is not None
    ts, val = result
    assert ts == 1600000200
    assert val == 0.25


def test_parse_csv_like_list():
    """Test parsing CSV-like string list."""
    data = [
        "turtlebp,1600000300,0.37",
        "turtlebp,1600000400,0.45",
        "other,1600000400,0.30"
    ]
    
    result = _parse_possible_structures(data, "turtlebp")
    assert result is not None
    ts, val = result
    assert ts == 1600000400
    assert val == 0.45


def test_parse_target_not_found():
    """Test parsing when target name not found."""
    data = [
        {"name": "other", "data": [[1600000000, 0.3]]}
    ]
    
    result = _parse_possible_structures(data, "turtlebp")
    assert result is None


def test_parse_empty_data():
    """Test parsing empty data."""
    result = _parse_possible_structures([], "turtlebp")
    assert result is None
    
    result = _parse_possible_structures({}, "turtlebp")
    assert result is None


def test_parse_malformed_data():
    """Test parsing malformed data doesn't crash."""
    # Should return None or handle gracefully
    result = _parse_possible_structures("invalid", "turtlebp")
    assert result is None
    
    result = _parse_possible_structures([{"invalid": "data"}], "turtlebp")
    assert result is None