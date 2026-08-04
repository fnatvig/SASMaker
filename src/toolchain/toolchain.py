import os
import subprocess
import sys
import time
from multiprocessing import Process


def server_port(uid, ied_index):
    """Return an MMS port unique to the Linux user and IED."""
    user_slot = uid - 1000

    if not 1 <= user_slot <= 99:
        raise RuntimeError(
            f"UID {uid} is outside the supported workshop range 1001-1099"
        )

    if not 1 <= ied_index <= 98:
        raise ValueError("IED index must be between 1 and 98")

    return 10000 + (user_slot * 100) + ied_index + 1


def run_one_toolchain(folder, interface, timestamp, port, duration):
    cmd = [
        f"./{folder}/goose_publisher_toolchain",
        interface,
        str(timestamp + 2),
        str(port),
        folder,
        str(duration),
    ]

    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    timestamp = int(round(time.time() * 1_000_000)) / 1_000_000
    print(timestamp)

    interface_base = os.environ.get("SASMAKER_INTERFACE")
    expected_interface = f"sm{os.getuid()}"

    if interface_base != expected_interface:
        raise RuntimeError(
            f"SASMAKER_INTERFACE must be the current user's interface "
            f"{expected_interface}"
        )

    folders = sys.argv[1:-1]
    duration = sys.argv[-1]

    processes = []

    for index, folder in enumerate(folders, start=1):
        process = Process(
            target=run_one_toolchain,
            args=(
                folder,
                f"{interface_base}.{index}",
                timestamp,
                server_port(os.getuid(), index),
                duration,
            ),
        )
        process.start()
        processes.append(process)

    for process in processes:
        process.join()

    return 1 if any(process.exitcode != 0 for process in processes) else 0


if __name__ == "__main__":
    sys.exit(main())