#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

workshop_user=${SUDO_USER:-}
if [ -z "$workshop_user" ] || [ "$workshop_user" = root ]; then
    echo "Run with sudo from the workshop user's account." >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname "$script_dir")
helper=/usr/local/libexec/sasmaker-network
sudoers_file="/etc/sudoers.d/sasmaker-$workshop_user"

install -o root -g root -m 0755 "$script_dir/sasmaker-network" "$helper"

{
    printf '%s ALL=(root) NOPASSWD: %s create *, %s cleanup *\n' \
        "$workshop_user" "$helper" "$helper"
} > "$sudoers_file"
chmod 0440 "$sudoers_file"
visudo -cf "$sudoers_file" >/dev/null

found=0
for publisher in "$repo_dir"/src/toolchain/IED*/goose_publisher_toolchain; do
    if [ -f "$publisher" ]; then
        setcap cap_net_raw+ep "$publisher"
        found=1
    fi
done

if [ "$found" -eq 0 ]; then
    echo "No compiled GOOSE publishers were found." >&2
    exit 1
fi

echo "SASMaker workshop networking installed for $workshop_user."
