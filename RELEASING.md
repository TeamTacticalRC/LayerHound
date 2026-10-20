# Releasing LayerHound

Releases go to the public [layerhound-releases](https://github.com/TeamTacticalRC/layerhound-releases) repo. LayerHound boards check it once a day, and an admin installs an update with **Settings → Updates → Update now**.

## Before the first release

- **Release key:** `~/.layerhound/release-signing.key` on the release Mac. **Keep a backup in your password manager.** Boards only install packages signed with it. If it's lost, boards need a manual deploy with a new public key (`PUBLIC_KEY` in `backend/updates.py`).
- **GitHub CLI** signed in (`gh auth status`) with access to TeamTacticalRC.

## Publishing a release

1. Make sure everything is committed on `main`, tested and working on your own board.
2. Write the release notes in a file, for example `notes.md`. Customers see them in Settings, so keep them short and plain.
3. Run, from the project folder:

```bash
backend/.venv/bin/python scripts/release.py 0.6.0 --notes-file notes.md
```

The script:
- sets the version
- builds the dashboard and runs the tests
- commits "Release v0.6.0" and tags it
- packages and signs the release

It then asks before publishing. Answering `y` pushes the tag and creates the public release.

## When the board setup changed

If a release changes `deploy/setup.sh` (system packages, permissions, services), add `--needs-setup`. The script warns you if `setup.sh` changed since the previous release.

Boards then don't offer one-click for that release. Instead, **Settings → Updates** shows a command (with a Copy button) for the owner to run on the board, over SSH or with a keyboard and screen:

```bash
curl -fsSL https://github.com/TeamTacticalRC/layerhound-releases/releases/latest/download/install.sh | bash -s -- --update
```

It downloads and verifies the release, then does what one-click does (database backup, new code with data and settings kept, restart, automatic rollback), then runs the new board setup, which asks for their password. Say so in the release notes' Updating section, and update your own board this way first, before announcing the release.

## Version numbers

Use `MAJOR.MINOR.PATCH`:
- **patch** (0.6.1) for fixes
- **minor** (0.7.0) for new features
- **major** once there are compatibility promises to keep

## The Docker image

Pushing the release tag (the script does this) makes GitHub build the Docker image for Intel/AMD and ARM, and publish it as `ghcr.io/teamtacticalrc/layerhound` with the version, `MAJOR.MINOR` and `latest` tags. Check the **Docker image** run under the repository's Actions tab.

The package is public: GitHub linked it to the public LayerHound repository automatically when v1.1.0 was published. Anyone can pull it without signing in. If a future image ever can't be pulled, check its visibility under the package's **Package settings** on GitHub.

## The card image

Publishing a release also makes GitHub build the **LayerHound card image** for the ROCK 4D. The workflow lives in the releases repo ([`layerhound-releases/.github/workflows/card-image.yml`](https://github.com/TeamTacticalRC/layerhound-releases/blob/main/.github/workflows/card-image.yml)), so it can add files to its own releases without any token. It runs on one of GitHub's free arm64 machines, takes the release's signed package and this repo's [`deploy/image/build-image.sh`](deploy/image/README.md) at the same version tag, and adds `layerhound-X.Y.Z-rock-4d.img.xz` and its `.sha256` to the release as a free download. It takes about 30–60 minutes: check the **Card image** run under the releases repo's Actions tab.

To build one by hand (for example, to rebuild an image), open **layerhound-releases → Actions → Card image → Run workflow** and enter the version. Without **Upload**, the image is kept on the run for 3 days instead.
