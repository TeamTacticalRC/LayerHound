# Contributing to LayerHound

Thanks for helping! LayerHound is made by Team Tactical RC and is free software under the [AGPL-3.0](LICENSE). Bug reports, ideas, testing and code are all welcome.

## Ways to help

- **Report a bug:** open a [bug report](https://github.com/TeamTacticalRC/LayerHound/issues/new/choose). In LayerHound, **Settings → System → Recent problems → Report a bug on GitHub** fills in the version and recent problems for you (with names and addresses left out). Reports are public: leave out passwords, access codes and anything private.
- **Suggest an idea:** open an [idea or feature request](https://github.com/TeamTacticalRC/LayerHound/issues/new/choose).
- **Test with your printers.** LayerHound is tested on Klipper (Snapmaker U1, Elegoo Neptune 4 Max, Creality K2 Plus) and a Bambu Lab P1S. **OctoPrint owners are especially welcome**: printer controls are built for OctoPrint but haven't been tried on a real one yet.
- **Improve the docs:** the [owner's guide](docs/GUIDE.md) is for people who don't program, so plain, short wording matters more than completeness.
- **Write code:** see below.
- **Security problems:** please **don't** open a public issue. Report them privately (see [SECURITY.md](SECURITY.md)).

## Before you write code

- **For anything bigger than a small fix, open an issue first** and say what you'd like to change. That saves you work if it doesn't fit, or is already being done.
- **Keep pull requests small:** one change per pull request. A small pull request gets reviewed quickly; a big one may sit.
- **No new dependencies without asking.** LayerHound runs on small boards, and every package is something to keep secure and up to date.

## Setting up

You'll need Python 3.10+ and Node.js 20+ on macOS or Linux. See **Develop: run it on your computer** in the [README](README.md#develop-run-it-on-your-computer).

**One copy at a time:** Bambu P1-series printers accept only one local connection, so stop any other LayerHound (on a board or another computer) watching the same Bambu printer while you develop.

## Making a change

- **Match the code around you:** the same style, naming and comment density. The Python is compact on purpose; follow what's there rather than reformatting.
- **Text people read is plain English:** short sentences, no jargon, say what to do. Error messages say what went wrong and what to try ("Check the address and port"), never a stack trace.
- **Add or update tests** for what you change (`backend/tests`, and `tests/ui` for the dashboard). The tests must pass:
  ```bash
  cd backend && .venv/bin/python -m pytest -q tests
  npm run build && backend/.venv/bin/python -m pytest -q tests/ui
  ```
- **Update the docs** (README, owner's guide) when you change what people see or do.
- **Use plain commit messages:** what changed and why.

GitHub runs the backend tests (Python 3.10 and 3.12), the frontend build, the browser tests, a check of the deploy scripts (shellcheck) and CodeQL on every pull request. They need to pass.

## How pull requests are reviewed

Every pull request is read in full by the maintainer, who is the only one who merges for now. Expect questions; they're not a "no".

**These areas get extra care,** because a mistake there can hurt people's boards or privacy. Changes to them need a clear reason, tests and a careful review, and may take longer:
- **Installing and updating:** `deploy/` (install.sh, setup.sh, install-code.sh), `backend/updates.py`, `backend/updater.py`, release signing and checks.
- **Sign-in and permissions:** `backend/auth.py`, roles, sessions, access keys, the recovery key.
- **Anything that runs commands** (subprocess, `sudo`, `systemctl`, `nmcli`, `tailscale`) or touches **file paths** (the Files folder, uploads, backups).
- **Network calls**, especially new places LayerHound connects to outside your network. LayerHound keeps your data at home: new outside connections need a very good reason and must be opt-in.
- **Printer controls:** anything that pauses, cancels or starts prints. These must stay off by default, admin-only, confirmed first, and only report success once the printer confirms it.
- **Stored secrets:** access codes, tokens and keys (`backend/vault.py`). They must never reach the browser or the logs.

Maintainers: write access is not handed out quickly. Read the whole diff, run it, and be extra careful with the areas above.

## Licensing of contributions

By opening a pull request, you confirm that:
- you wrote the contribution, or have the right to contribute it;
- it's licensed under the project's [AGPL-3.0](LICENSE); and
- you grant Team Tactical RC permission to also distribute your contribution under other license terms in the future (for example, alongside a commercial version of LayerHound), while it stays available under the AGPL-3.0 here.

Add a line saying so to your first pull request, for example: *"I agree to the licensing terms in CONTRIBUTING.md."*

## The LayerHound name and logo

The LayerHound name, logo and mascot aren't covered by the AGPL. You're welcome to fork LayerHound, but forks need their own name and logo: see [TRADEMARKS.md](TRADEMARKS.md).

## Be kind

Be respectful and patient with everyone: people here range from first-time contributors to long-time developers, and many are print-farm owners rather than programmers. Harassment or personal attacks aren't tolerated; the maintainer may remove comments or block people who don't follow this.
