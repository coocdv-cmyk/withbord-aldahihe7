# CI template

`ci.yml` in this folder is the reviewed CI workflow for this repository.

## Enabling it

Changing a file under `.github/workflows/` needs a GitHub token with the
`workflow` scope. The push token configured for this machine does not have
it, so the workflow cannot be committed from here.

To enable it:

1. Open the repository on GitHub → **Add file** → **Create new file**.
2. Path: `.github/workflows/ci.yml`
3. Paste the contents of `tools/ci/ci.yml`.
4. Delete `.github/workflows/django.yml` (the GitHub Django template: it runs
   `python manage.py test`, and this repository has no `manage.py` and no
   root `requirements.txt`, so it fails on every push).

Alternatively refresh the local token with the scope and push it yourself:

```powershell
gh auth refresh -h github.com -s workflow
```

## What it runs

| Step | Command |
|---|---|
| Dependencies | `pip install -r rasm-pro/requirements.txt` + `pytest` |
| Compile check | `python -m compileall -q rasm-pro/engine rasm-pro/rasm.py rasm-pro/tools studio` |
| Tests | `python -m pytest -q tests` (inside `rasm-pro/`) |

`ubuntu-latest` already ships `ffmpeg` and `ffprobe`. The engine treats them
as external sidecars (never bundled). If they are missing, the tests that
need them are **skipped explicitly** instead of failing — see
`rasm-pro/tests/conftest.py`.
