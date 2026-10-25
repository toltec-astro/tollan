"""Fake Slurm commands for scheduler tests."""

import json
import sys

import pytest

FAKE_COMMAND = f"""#!{sys.executable}
import json, os, subprocess, sys, time
name = os.path.basename(sys.argv[0])
state_path = os.environ["FAKE_SLURM_STATE"]
with open(state_path + ".log", "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\\n")
with open(state_path) as stream:
    reply = json.load(stream).get(name, {{}})
time.sleep(reply.get("sleep", 0))
if name == "ssh" and not reply.get("exit"):
    os.execv("/bin/sh", ["/bin/sh", "-c", sys.argv[-1]])
if name == "sbatch" and reply.get("run"):
    options = dict(arg[2:].split("=", 1) for arg in sys.argv[1:-1] if "=" in arg)
    with open(options["output"], "ab") as output:
        subprocess.run(["/bin/sh", sys.argv[-1]], cwd=options["chdir"], stdout=output)
sys.stdout.write(reply.get("stdout", ""))
sys.stderr.write(reply.get("stderr", ""))
sys.exit(reply.get("exit", 0))
"""


class FakeSlurm:
    """Fake scheduler commands on PATH, with replies and a call log.

    Each command logs its arguments and prints its configured reply. ``ssh``
    runs its command locally; ``sbatch`` with ``run=True`` runs the job script
    before replying.
    """

    def __init__(self, path):
        self.state = path / "state.json"
        self.replies = {}
        self.save()

    def reply(self, name, **reply):
        """Set the reply of a command."""
        self.replies[name] = reply
        self.save()

    def save(self):
        """Write the replies for the fake commands."""
        self.state.write_text(json.dumps(self.replies))

    @property
    def calls(self):
        """Commands called so far, with their arguments."""
        log = self.state.with_name("state.json.log")
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def commands(self):
        """Names of the commands called so far."""
        return [call[0] for call in self.calls]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Put fake ``ssh`` and Slurm commands first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "sbatch", "sacct", "squeue", "sinfo", "scancel"):
        path = bin_dir / name
        path.write_text(FAKE_COMMAND)
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("FAKE_SLURM_STATE", str(tmp_path / "state.json"))
    return FakeSlurm(tmp_path)
