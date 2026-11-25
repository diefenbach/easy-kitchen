import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI_CD = ROOT / ".github" / "workflows" / "ci-cd.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
DOCKERFILE = ROOT / "Dockerfile"
PRODUCTION_SETTINGS = ROOT / "src" / "project" / "settings" / "production.py"


def test_image_uses_a_single_build_stage_and_defaults_to_runserver():
    dockerfile = DOCKERFILE.read_text()
    assert dockerfile.count("FROM ") == 1
    assert "ENTRYPOINT" not in dockerfile
    assert 'CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in dockerfile
    assert "mkdir -p /app/src/staticfiles /app/src/media" in dockerfile
    assert "USER app" in dockerfile


def test_ci_cd_deploys_only_when_runtime_paths_change():
    workflow = CI_CD.read_text()

    assert "dorny/paths-filter@v3" in workflow
    assert "needs.changes.outputs.deploy == 'true'" in workflow
    assert "- 'src/**'" in workflow


def test_images_are_tagged_with_commit_date_and_short_sha():
    workflow = CI_CD.read_text()

    assert "--date=format-local:%Y%m%d" in workflow
    assert "git rev-parse --short=7 HEAD" in workflow
    assert "ghcr.io/diefenbach/easy-kitchen" in workflow


def test_every_build_is_probed_under_production_settings():
    workflow = CI_CD.read_text()

    assert "DJANGO_SETTINGS_MODULE=project.settings.production" in workflow
    assert "python manage.py check" in workflow
    assert "python manage.py migrate --noinput" in workflow
    assert "import project.wsgi" in workflow
    assert "python manage.py collectstatic --noinput" in workflow


def test_probe_sets_every_required_production_variable():
    required = re.findall(r'required\("([A-Z_]+)"\)', PRODUCTION_SETTINGS.read_text())
    workflow = CI_CD.read_text()

    assert required
    for name in required:
        assert f"-e {name}=" in workflow, name


def test_only_main_pushes_images_and_keeps_the_last_ten():
    workflow = CI_CD.read_text()

    assert "actions/delete-package-versions@v5" in workflow
    assert "min-versions-to-keep: 10" in workflow
    assert "uses: ./.github/workflows/deploy.yml" in workflow


def test_deploy_runs_the_restricted_server_script_with_a_tag():
    workflow = DEPLOY.read_text()

    assert "workflow_call:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "BatchMode=yes" in workflow
    assert 'iqpp@46.101.162.117 deploy kitchen "$TAG"' in workflow
    assert "scp " not in workflow


def test_the_old_self_copied_deploy_script_is_gone():
    assert not (ROOT / ".github" / "scripts" / "deploy.sh").exists()
