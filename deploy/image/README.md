# LayerHound card image (ROCK 4D)

A microSD card image with LayerHound already installed: Radxa's own OS for the ROCK 4D plus the latest signed LayerHound release. Put the card in the board, plug in power (and Ethernet if you have it), and open `http://layerhound.local`. With no network, the board opens the **LayerHound-Setup** Wi-Fi instead.

## Building it

Run on an arm64 Linux computer (a ROCK 4D, a Raspberry Pi, or GitHub's arm64 runners) with about 15 GB free:

```bash
sudo deploy/image/build-image.sh
```

It downloads the tested Radxa OS image and the latest LayerHound release, checks both (Radxa's by checksum, LayerHound's by Team Tactical RC's signature), installs LayerHound into the image, and writes `layerhound-X.Y.Z-rock-4d.img.xz` and its `.sha256`. Options: `--package FILE` (a signed package), `--base FILE` (Radxa's image), `--out DIR`, `--keep-desktop`.

`--source DIR` builds a **test** image from an unpacked, unsigned LayerHound folder (for example `~/layerhound-src` on a board you deploy to). Test images are for testing only: never sell or share them.

## What's different from a normal install

- **Nothing secret is in the image.** Each card makes its own LayerHound encryption key, install ID, database and SSH host keys the first time it starts (`firstboot.sh`). The build stops if any of these are found in the image.
- **The board account (`radxa`) still has Radxa's default password,** expired: the first sign-in (over SSH or with a keyboard) asks for a new one. Radxa's second default account, `rock`, is locked. LayerHound's own sign-in is separate and made in the setup page.
- **The board is named `layerhound`.** A second LayerHound board on the same network shows up as `layerhound-2.local`.
- **No desktop:** the card starts without Radxa's desktop (`--keep-desktop` keeps it).
- **Tailscale is installed** and off until the owner connects it in Settings → Network.

## Testing a new image

1. Write the image to a spare microSD card (balenaEtcher or Raspberry Pi Imager).
2. Put it in a ROCK 4D, plug in Ethernet and power, wait 2–3 minutes, open `http://layerhound.local`.
3. Check: the first-run setup appears; LayerHound runs as `layerhound`; `ssh radxa@layerhound.local` asks for a new password; `/etc/layerhound/first-boot-done` exists; the partition grew to the whole card (`df -h /`).
4. Without Ethernet: the **LayerHound-Setup** Wi-Fi appears and the setup page opens on a phone.
5. Write a second card from the same image and check the two have different keys (`sudo sha256sum /var/lib/layerhound/data/secret.key /etc/ssh/ssh_host_ed25519_key.pub`).
