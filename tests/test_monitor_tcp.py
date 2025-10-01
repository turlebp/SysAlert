"""
Test TCP monitoring functionality.
"""
import pytest
import asyncio
from services.monitor import tcp_check


@pytest.mark.asyncio
async def test_tcp_check_timeout():
    """Test TCP check with timeout."""
    # Use an unroutable IP that will timeout
    ok, rtt, err = await tcp_check("10.255.255.1", 65535, timeout=0.5)
    
    assert ok is False
    assert rtt == 0.0
    assert "timeout" in err.lower() or "error" in err.lower()


@pytest.mark.asyncio
async def test_tcp_check_refused():
    """Test TCP check with connection refused."""
    # Connect to localhost on a port that's likely closed
    ok, rtt, err = await tcp_check("127.0.0.1", 59999, timeout=1.0)
    
    assert ok is False
    assert "refused" in err.lower() or "error" in err.lower()


@pytest.mark.asyncio
async def test_tcp_check_success_localhost():
    """
    Test successful TCP connection using a real server.
    This test creates a temporary server to accept connections.
    """
    async def handle_client(reader, writer):
        """Simple handler that immediately closes."""
        writer.close()
        await writer.wait_closed()
    
    # Create a simple TCP server
    server = await asyncio.start_server(
        handle_client,
        '127.0.0.1',
        0  # Random free port
    )
    
    # Get the port the server is listening on
    port = server.sockets[0].getsockname()[1]
    
    try:
        # Check against our test server
        ok, rtt, err = await tcp_check("127.0.0.1", port, timeout=2.0)
        
        assert ok is True
        assert rtt > 0
        assert err == ""
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tcp_check_returns_correct_types():
    """Ensure tcp_check returns correct types."""
    ok, rtt, err = await tcp_check("127.0.0.1", 59998, timeout=0.5)
    
    assert isinstance(ok, bool)
    assert isinstance(rtt, float)
    assert isinstance(err, str)