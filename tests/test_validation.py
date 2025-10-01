"""
Test input validation helpers.
"""
import pytest
import ipaddress


def test_ip_validation():
    """Test IP address validation."""
    # Valid IPs
    assert ipaddress.ip_address("192.168.1.1")
    assert ipaddress.ip_address("10.0.0.1")
    assert ipaddress.ip_address("2001:db8::1")
    
    # Invalid IPs should raise
    with pytest.raises(ValueError):
        ipaddress.ip_address("999.999.999.999")
    
    with pytest.raises(ValueError):
        ipaddress.ip_address("not_an_ip")


def test_port_validation():
    """Test port number validation."""
    def validate_port(port):
        p = int(port)
        return 1 <= p <= 65535
    
    assert validate_port(80)
    assert validate_port(443)
    assert validate_port(9876)
    assert validate_port(1)
    assert validate_port(65535)
    
    assert not validate_port(0)
    assert not validate_port(65536)
    assert not validate_port(-1)