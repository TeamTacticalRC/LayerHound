# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Report them privately instead:

- Use GitHub's **Report a vulnerability** button on the [Security tab](https://github.com/TeamTacticalRC/LayerHound/security) of this repository.

Include what you found, how to reproduce it, and which version you were running. We'll confirm receipt within a few days, keep you updated while we work on a fix, and credit you when it's released (unless you'd rather stay anonymous).

## Supported versions

Security fixes go into the latest release. Please update before reporting, in case it's already fixed.

## Things to know

- **Sign-in is required** (unless the owner turns on local-network viewing), but LayerHound uses plain `http://`. Never expose its port to the internet; use a private network tool such as Tailscale for remote access.
- **Only download LayerHound from this repository's Releases page** (or layerhound.com once it exists). Copies from anywhere else may have been modified.
- Printer access codes, API keys and service tokens are stored encrypted in the local database (the key is a separate, owner-only file) and never sent to the browser. Backups can include them if you choose; keep those files private.
