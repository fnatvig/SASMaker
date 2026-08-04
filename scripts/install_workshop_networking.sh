#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname "$script_dir")
helper=/usr/local/libexec/sasmaker-network
workshop_group=sasmaker
sudoers_file=/etc/sudoers.d/sasmaker-workshop

if [ "$#" -eq 0 ]; then
    workshop_user=${SUDO_USER:-}
    if [ -z "$workshop_user" ] || [ "$workshop_user" = root ]; then
        echo "Pass at least one workshop username." >&2
        exit 1
    fi
    set -- "$workshop_user"
fi

getent group "$workshop_group" >/dev/null 2>&1 || groupadd --system "$workshop_group"
for workshop_user in "$@"; do
    if ! id "$workshop_user" >/dev/null 2>&1; then
        echo "Unknown workshop user: $workshop_user" >&2
        exit 1
    fi
    usermod -a -G "$workshop_group" "$workshop_user"
done

install -o root -g root -m 0755 "$script_dir/sasmaker-network" "$helper"

{
    printf '%%%s ALL=(root) NOPASSWD: %s create *, %s cleanup *\n' \
        "$workshop_group" "$helper" "$helper"
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

echo "SASMaker workshop networking installed for group $workshop_group."
echo "Users added: $*"
echo "Users must start a new login session before group membership takes effect."