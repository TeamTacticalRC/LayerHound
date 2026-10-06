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

If a release changes `deploy/setup.sh` (system packages, permissions, services), add `--needs-setup`. Boards will then say the update needs a full install, rather than offering one-click. The script warns you if `setup.sh` changed since the previous release.

## Version numbers

Use `MAJOR.MINOR.PATCH`:
- **patch** (0.6.1) for fixes
- **minor** (0.7.0) for new features
- **major** once there are compatibility promises to keep

## The Docker image

Pushing the release tag (the script does this) makes GitHub build the Docker image for Intel/AMD and ARM, and publish it as `ghcr.io/teamtacticalrc/layerhound` with the version, `MAJOR.MINOR` and `latest` tags. Check the **Docker image** run under the repository's Actions tab.

The package is public: GitHub linked it to the public LayerHound repository automatically when v1.1.0 was published. Anyone can pull it without signing in. If a future image ever can't be pulled, check its visibility under the package's **Package settings** on GitHub.
