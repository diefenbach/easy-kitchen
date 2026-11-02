import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOY_SH = ROOT / ".github" / "scripts" / "deploy.sh"
CI_CD = ROOT / ".github" / "workflows" / "ci-cd.yml"
DOCKERFILE = ROOT / "Dockerfile"


def test_deploy_script_is_valid_shell():
    subprocess.run(["sh", "-n", str(DEPLOY_SH)], check=True)


def test_deployment_does_not_require_a_static_init_service():
    assert "kitchen-static-init" not in DEPLOY_SH.read_text()
    dockerfile = DOCKERFILE.read_text()
    assert "mkdir -p /app/src/staticfiles /app/src/media" in dockerfile
    assert "USER app" in dockerfile


def test_image_uses_a_single_build_stage_and_defaults_to_runserver():
    dockerfile = DOCKERFILE.read_text()
    assert dockerfile.count("FROM ") == 1
    assert "ENTRYPOINT" not in dockerfile
    assert 'CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in dockerfile


def test_ci_cd_deploys_only_when_runtime_paths_change():
    workflow = CI_CD.read_text()

    assert "dorny/paths-filter@v3" in workflow
    assert "needs.changes.outputs.deploy == 'true'" in workflow
    assert "- 'src/**'" in workflow


def test_deploy_script_waits_for_kitchen_and_mcp():
    script = DEPLOY_SH.read_text()

    assert "wait_for \"kitchen\" kitchen_ready" in script
    assert "wait_for \"kitchen-mcp\" mcp_ready" in script
    assert "https://kitchen.iqpp.de/" in script
    assert "socket.create_connection(('127.0.0.1', 8000), 2)" in script
    assert "urllib.request" not in script
    assert "--retry 8" not in script
    assert "registry.iqpp.de/iqpp/easykitchen" not in script
    assert "python manage.py migrate --noinput" in script
    assert "python manage.py collectstatic --noinput --clear" in script
