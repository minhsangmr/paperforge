# Paperforge Week 0 — exact setup guide

This guide assumes an Intel Mac running macOS Monterey. macOS is only the host
for VS Code, Git, Docker Desktop, Make, and the browser. All Python and uv work
happens inside a Linux container.

## 0. Expected result

At the end of Week 0:

- the repository is named `paperforge`;
- `main` is pushed to GitHub;
- VS Code is attached to the Linux `workspace` container;
- Python reports Linux and version 3.12;
- `make check` passes;
- `GET /api/v1/health/live` returns HTTP 200;
- GitHub Actions passes on `main`.

## 1. Create the local project directory

Extract the supplied scaffold into a normal source-code directory, not Desktop,
Downloads, iCloud Drive, Dropbox, or OneDrive. A recommended location is:

```bash
mkdir -p ~/Developer
cd ~/Developer
unzip ~/Downloads/paperforge-week0.zip
mv paperforge-week0 paperforge
cd paperforge
cp .env.example .env
```

Avoid spaces and accented characters in the path.

## 2. Configure Git on macOS

Git is intentionally a host tool. Check it:

```bash
git --version
```

If macOS offers to install Command Line Tools, accept it. Then configure your
real name and the email connected to GitHub:

```bash
git config --global user.name "YOUR FULL NAME"
git config --global user.email "YOUR_GITHUB_EMAIL"
git config --global init.defaultBranch main
git config --global fetch.prune true
git config --global pull.ff only
```

Verify:

```bash
git config --global --list
```

### Configure SSH authentication

Check whether a key already exists:

```bash
ls -al ~/.ssh
```

If `id_ed25519` and `id_ed25519.pub` already exist and belong to you, reuse them.
Otherwise create a key:

```bash
ssh-keygen -t ed25519 -C "YOUR_GITHUB_EMAIL"
```

Press Enter to use `~/.ssh/id_ed25519` and set a passphrase. Configure macOS
Keychain support:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/config
chmod 600 ~/.ssh/config
cat >> ~/.ssh/config <<'SSHCONFIG'
Host github.com
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
SSHCONFIG

ssh-add --apple-use-keychain ~/.ssh/id_ed25519
pbcopy < ~/.ssh/id_ed25519.pub
```

In GitHub, open **Settings → SSH and GPG keys → New SSH key**, paste the key,
and save it. Test:

```bash
ssh -T git@github.com
```

The first connection may ask you to confirm GitHub's host fingerprint.

## 3. Configure Docker Desktop

Use the Intel build of Docker Desktop. Monterey is outside the currently
supported macOS range for the newest Docker Desktop releases, so keep a known
working Intel installer and do not enable automatic upgrades blindly.

After launching Docker Desktop:

1. Open **Settings → General** and enable starting Docker Desktop at login only
   when you use it frequently.
2. Open **Settings → Resources**.
3. For an 8 GB Mac, start with 2 CPUs and 4 GB memory. For a 16 GB-or-more
   Mac, use about 4 CPUs and 6–8 GB memory. Keep at least 30 GB disk available.
4. Add `~/Developer` to file sharing if Docker cannot bind-mount the project.
5. Keep Kubernetes disabled; Paperforge does not need it.
6. Keep Resource Saver enabled when available.

Verify from macOS Terminal:

```bash
docker version
docker compose version
docker run --rm --platform linux/amd64 alpine uname -a
```

The last command must report Linux and `x86_64`/`amd64`.

## 4. Configure VS Code

Install these host extensions. In VS Code, also run **Shell Command: Install
'code' command in PATH** from the Command Palette when `code` is unavailable:



- Dev Containers
- Docker
- GitHub Pull Requests and Issues

The Python, Ruff, and MyPy extensions are declared in `.devcontainer` and are
installed inside the remote container automatically.

Open the project:

```bash
code ~/Developer/paperforge
```

In VS Code:

1. Open the Command Palette with `Cmd+Shift+P`.
2. Run **Dev Containers: Reopen in Container**.
3. Wait for the lower-left status indicator to show `Dev Container: Paperforge Linux Development`.
4. Open the integrated terminal.
5. Confirm the prompt is inside `/workspace`.

Inside the VS Code terminal, run:

```bash
uname -a
uv --version
uv run python --version
uv run python -c "import sys; print(sys.platform)"
```

Expected results are Linux, uv, Python 3.12, and `linux`.

Never select a Python interpreter under `/usr/bin/python` on the Mac. The VS
Code interpreter must be `/workspace/.venv/bin/python`.

## 5. Bootstrap the repository

From a normal macOS terminal at the project root:

```bash
cp .env.example .env
make verify-host
make bootstrap
make container-info
make compose-config
```

`make bootstrap` builds the Linux development image. On the first run it creates
`uv.lock` with `uv lock` inside Linux, then runs `uv sync --frozen`. On later runs
it only performs the frozen sync. It never uses host Python or host uv.

The VS Code container is a dedicated long-running `workspace` service. Start the
separate API service from a macOS terminal:

```bash
make up
make ps
make logs
```

Use another terminal for:

```bash
make health
curl http://localhost:8000/api/v1/health/live
```

Expected JSON:

```json
{"status":"ok","service":"paperforge","version":"0.1.0"}
```

Open `http://localhost:8000/docs` in the browser.

## 6. Run all quality gates

```bash
make format
make check
```

Every command is routed through Docker Compose. Verify this by reading the
Makefile: Python tools always use `docker compose run`.

Useful commands:

```bash
make shell        # Linux shell with project bind-mounted
make test         # unit tests
make test-cov     # coverage gate
make lint         # Ruff
make typecheck    # strict MyPy
make logs         # API logs
make down         # stop, keep data
make reset        # stop and delete project volumes
```

## 7. Initialize Git with clean Week 0 commits

Do not copy the `.git` directory from the teacher's project. Build your own
history from the clean Paperforge directory.

```bash
git init -b main
git status
git add LICENSE NOTICE.md README.md .gitignore .dockerignore .editorconfig
git commit -m "chore: initialize paperforge repository with attribution"

make bootstrap
make container-info

git add pyproject.toml uv.lock Dockerfile compose.yaml Makefile .python-version .env.example scripts/
git commit -m "build: add container-only uv development environment"

git add src/ tests/
git commit -m "feat(api): add versioned liveness endpoint"

git add .vscode/ .devcontainer/
git commit -m "chore(dev): configure VS Code dev container"

git add .github/ docs/
git commit -m "ci: add Docker-based quality gates"
```

Inspect before pushing:

```bash
git status
git log --oneline --decorate --graph
git grep -nE '(ghp_|github_pat_|sk-[A-Za-z0-9]|BEGIN .*PRIVATE KEY|api[_-]?key[[:space:]]*=)' -- ':!*.md'
```

The working tree must be clean and `.env` must not appear in `git status`.

## 8. Create the GitHub repository

On GitHub create a repository named `paperforge`.

Recommended choices:

- visibility: public when you are ready for attribution and README to be seen;
- do not initialize with README;
- do not add `.gitignore`;
- do not add a license because the local repository already contains one.

Copy the SSH URL, then run:

```bash
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/paperforge.git
git remote -v
git push -u origin main
```

Alternative with GitHub CLI, when `gh` is already installed and authenticated:

```bash
gh auth login
gh repo create paperforge --public --source=. --remote=origin --push
```

Do not install GitHub CLI solely for this step; the browser plus Git is enough.

## 9. Configure the GitHub repository

After the first push:

1. Open **Actions** and confirm the `CI` workflow passes.
2. Open **Settings → General** and disable Wiki unless you plan to use it.
3. Open **Settings → Branches/Rules** and add a rule for `main`:
   - require a pull request before merging;
   - require the `Container quality gates` status check;
   - require branches to be up to date before merging;
   - block force pushes and deletions.
4. Enable Dependabot alerts and security updates. Version updates for uv, Docker,
   and GitHub Actions are already configured in `.github/dependabot.yml`.
5. Add repository topics such as `rag`, `fastapi`, `docker`, `uv`, `opensearch`,
   and `llm` only as those features actually exist.
6. Do not add fake screenshots or claim unfinished services.

For a solo project, create short feature branches and merge them through pull
requests. This creates an auditable project history suitable for interviews.

## 10. Week 0 acceptance checklist

Run from macOS:

```bash
make verify-host
make bootstrap
make container-info
make compose-config
make up
make check
make health
git status
```

Pass criteria:

- host verification succeeds;
- container kernel is Linux;
- container Python is 3.12;
- uv lock is frozen and sync succeeds;
- Compose configuration validates;
- formatting, linting, strict typing, tests, and coverage all pass;
- health endpoint returns HTTP 200;
- `git status` is clean;
- GitHub CI is green.

## 11. Troubleshooting

### Docker daemon is unavailable

Start Docker Desktop and wait until its status says the engine is running, then:

```bash
docker info
```

### Bind mount is empty or permission denied

Move the project under `~/Developer`, add that parent directory to Docker file
sharing, then restart Docker Desktop.

### `.venv` contains macOS files

Delete only the Docker volume and rebuild:

```bash
make reset
rm -rf .venv
make bootstrap
```

The local `.venv` path is ignored by Git. Never run `uv sync` directly on macOS.

### Port 8000 is already used

Find the host process/container:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Stop the conflicting process or change the host side of `8000:8000` in
`compose.yaml`, for example to `8001:8000`.

### OpenSearch consumes too much memory

Do not start the `search` profile during Week 0. `make up` starts only the API.
OpenSearch is first required for the search phase.
