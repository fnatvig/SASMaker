from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from sasmaker.util import capture_to_pcap


def test_capture_rejects_existing_output(tmp_path):
    output = tmp_path / "capture.pcap"
    output.write_bytes(b"existing")

    with patch("sasmaker.util.shutil.which", return_value="/usr/bin/dumpcap"):
        with pytest.raises(FileExistsError):
            capture_to_pcap([SimpleNamespace(name="IED1")], 10, output)


def test_capture_runs_publishers_and_cleans_up(tmp_path):
    toolchain = tmp_path / "toolchain"
    toolchain.mkdir()
    (toolchain / "toolchain.py").touch()
    output = tmp_path / "capture.pcap"

    capture_process = Mock()
    capture_process.poll.return_value = None
    capture_process.wait.return_value = 0
    publisher_process = Mock()
    publisher_process.wait.return_value = 0

    def create_capture(*_args, **_kwargs):
        output.write_bytes(b"pcap header and captured packet data")
        return capture_process

    with (
        patch("sasmaker.util.shutil.which", return_value="/usr/bin/dumpcap"),
        patch("sasmaker.util.create_interfaces") as create_interfaces,
        patch("sasmaker.util.subprocess.Popen", side_effect=create_capture) as popen,
        patch("sasmaker.util.spawn_script", return_value=publisher_process) as spawn_script,
        patch("sasmaker.util._cleanup_interfaces") as cleanup_interfaces,
    ):
        result = capture_to_pcap(
            [SimpleNamespace(name="IED1"), SimpleNamespace(name="IED2")],
            10,
            output,
            toolchain_directory=toolchain,
        )

    assert result == output.resolve()
    create_interfaces.assert_called_once()
    assert popen.call_args.args[0] == [
        "/usr/bin/dumpcap",
        "-q",
        "-F",
        "pcap",
        "-i",
        "veth1",
        "-w",
        str(output.resolve()),
    ]
    spawn_script.assert_called_once_with(
        cwd=toolchain.resolve(),
        py_paths=[str(toolchain.resolve())],
        args=["IED1", "IED2", "10"],
    )
    cleanup_interfaces.assert_called_once_with(2)
    capture_process.send_signal.assert_called_once()


def test_capture_cleans_up_when_publisher_fails(tmp_path):
    toolchain = tmp_path / "toolchain"
    toolchain.mkdir()
    (toolchain / "toolchain.py").touch()
    output = tmp_path / "capture.pcap"

    capture_process = Mock()
    capture_process.poll.return_value = None
    capture_process.wait.return_value = 0
    publisher_process = Mock()
    publisher_process.wait.return_value = 1

    def create_capture(*_args, **_kwargs):
        output.write_bytes(b"pcap header and captured packet data")
        return capture_process

    with (
        patch("sasmaker.util.shutil.which", return_value="/usr/bin/dumpcap"),
        patch("sasmaker.util.create_interfaces"),
        patch("sasmaker.util.subprocess.Popen", side_effect=create_capture),
        patch("sasmaker.util.spawn_script", return_value=publisher_process),
        patch("sasmaker.util._cleanup_interfaces") as cleanup_interfaces,
    ):
        with pytest.raises(RuntimeError, match="exited with status 1"):
            capture_to_pcap(
                [SimpleNamespace(name="IED1")],
                10,
                output,
                toolchain_directory=toolchain,
            )

    cleanup_interfaces.assert_called_once_with(1)
    capture_process.send_signal.assert_called_once()
