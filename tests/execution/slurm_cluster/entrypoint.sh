#!/bin/sh
# Start one role of the Slurm test cluster: "controller" or "compute".
set -eu

wait_for() {
    for _ in $(seq 1 60); do
        if "$@" >/dev/null 2>&1; then return 0; fi
        sleep 1
    done
    echo "timed out: $*" >&2
    exit 1
}

install -d -o munge -g munge -m 755 /run/munge
runuser -u munge -- /usr/sbin/munged

case "$1" in
controller)
    mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld
    mysqld_safe >/dev/null 2>&1 &
    wait_for mysqladmin ping
    mysql -e "CREATE DATABASE IF NOT EXISTS slurm_acct_db;
        CREATE USER IF NOT EXISTS 'slurm'@'localhost' IDENTIFIED BY 'slurm';
        GRANT ALL ON slurm_acct_db.* TO 'slurm'@'localhost';"
    slurmdbd
    wait_for sacctmgr -n list cluster
    sacctmgr -i add cluster tollan >/dev/null 2>&1 || true
    slurmctld
    wait_for scontrol ping
    sacctmgr -i add account group >/dev/null 2>&1 || true
    sacctmgr -i add user tester account=group >/dev/null 2>&1 || true
    install -d -o tester -g tester -m 700 /home/tester/.ssh
    install -o tester -g tester -m 600 "$SHARED/ssh/id_ed25519.pub" \
        /home/tester/.ssh/authorized_keys
    exec /usr/sbin/sshd -D -e
    ;;
compute)
    exec slurmd -D -N "$(hostname)"
    ;;
esac
