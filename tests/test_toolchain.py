import pytest

from toolchain.toolchain import server_port


def test_server_ports_are_unique_per_user_and_ied():
    assert server_port(1001, 1) == 10102
    assert server_port(1001, 3) == 10104
    assert server_port(1002, 1) == 10202
    assert server_port(1020, 3) == 12004


def test_server_port_rejects_non_workshop_uid():
    with pytest.raises(RuntimeError, match="supported workshop account range"):
        server_port(1000, 1)
