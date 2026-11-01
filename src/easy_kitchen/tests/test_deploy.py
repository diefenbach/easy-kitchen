import subprocess
from pathlib import Path

DEPLOY_SH = Path(__file__).resolve().parents[3] / ".github" / "scripts" / "deploy.sh"


def test_deploy_script_is_valid_shell():
    subprocess.run(["sh", "-n", str(DEPLOY_SH)], check=True)


def test_deploy_script_waits_for_kitchen_and_mcp():
    script = DEPLOY_SH.read_text()

    assert "wait_for \"kitchen\" kitchen_ready" in script
    assert "wait_for \"kitchen-mcp\" mcp_ready" in script
    assert "https://kitchen.iqpp.de/" in script
    assert "socket.create_connection(('127.0.0.1', 8000), 2)" in script
    assert "urllib.request" not in script
    assert "--retry 8" not in script
