# Slurm test cluster for tollan.execution live tests (see compose.yaml).
FROM debian:trixie-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        slurm-wlm slurmdbd slurm-client munge mariadb-server openssh-server \
        python3 python3-pip procps \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages dagster-pipes \
    && /usr/sbin/mungekey --force \
    && chown munge:munge /etc/munge/munge.key \
    && useradd --create-home --uid 1000 --shell /bin/bash tester \
    && mkdir -p /var/spool/slurmctld /var/spool/slurmd /var/log/slurm /run/sshd \
    && chown slurm:slurm /var/spool/slurmctld /var/spool/slurmd /var/log/slurm

COPY slurm.conf cgroup.conf /etc/slurm/
COPY --chown=slurm:slurm --chmod=600 slurmdbd.conf /etc/slurm/slurmdbd.conf
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
