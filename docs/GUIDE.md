# LayerHound owner's guide

LayerHound watches your 3D printers and the small server it runs on, all in one dashboard on your own network. This guide covers getting it running and using it day to day. No programming needed.

## Contents

- [Getting LayerHound running](#getting-layerhound-running)
- [First visit: your admin account](#first-visit-your-admin-account)
- [Adding printers](#adding-printers)
- [Around the dashboard](#around-the-dashboard)
- [Accounts and who can see what](#accounts-and-who-can-see-what)
- [Wi-Fi and the setup hotspot](#wi-fi-and-the-setup-hotspot)
- [Updates](#updates)
- [Backups](#backups)
- [Using LayerHound away from home](#using-layerhound-away-from-home)
- [Forgot your password?](#forgot-your-password)
- [Troubleshooting](#troubleshooting)
- [Feedback and help](#feedback-and-help)
- [Good to know](#good-to-know)

## Getting LayerHound running

### If you have a LayerHound board

1. Plug the board into your router with an Ethernet cable, and plug in the power.
2. Wait about two minutes, then open **http://layerhound.local** in a browser on the same network.

**No cable handy?** After a minute or so, the board creates its own Wi-Fi network called **LayerHound-Setup**. Join it from your phone, and a setup page opens. Pick your home Wi-Fi, enter its password, name your farm and create your admin account. The board then joins your Wi-Fi. Reconnect your phone to your Wi-Fi and open **http://layerhound.local**.

### Running it with Docker

If you already use Docker (on a Linux PC, a NAS, or Docker Desktop), download [docker-compose.yml](../docker-compose.yml), put it in a folder, and run `docker compose up -d` there. Then open **http://THIS-MACHINE:8080**.

- **Keep `network_mode: host`** on Linux, so network scans, device monitoring and printer suggestions see your real network. On Docker Desktop for Mac or Windows, use the `ports` lines instead; printers still work, but scans only see Docker's own network.
- **Your data** (database, encryption key, LayerHound Files) lives in the `layerhound-data` volume, and survives updates.
- **Updating:** Settings → Updates tells you when there's a new version. Run `docker compose pull && docker compose up -d` to install it.
- **Not in Docker:** Wi-Fi settings, the setup hotspot, the case fan and Shut down board, which are all for the LayerHound board.

### Installing on your own board

LayerHound runs on small Linux boards such as a Radxa ROCK or Raspberry Pi, or any always-on Debian-based computer.

1. Install **Debian 12**, Armbian, Raspberry Pi OS or Ubuntu on the board, and connect it to your network.
2. Open a terminal on the board, either over SSH or with a keyboard and screen.
3. Run:

```bash
curl -fsSL https://github.com/TeamTacticalRC/layerhound-releases/releases/latest/download/install.sh | bash
```

The installer:
- downloads the latest LayerHound and checks it's genuinely from Team Tactical RC
- uses port 80 unless you choose another: add `-s -- --port 8080` after `bash` if another program already uses port 80
- asks for your password (for `sudo`)
- offers to rename the board to `layerhound`

It takes a few minutes. When it finishes, open **http://layerhound.local**.

## First visit: your admin account

The first time you open LayerHound, it asks you to:

- **Name your farm.** This shows across the dashboard; you can change it later.
- **Create the admin account.** There are no default passwords. Use at least 8 characters, and keep the password somewhere safe.
- **Save your recovery key.** If you ever forget your password, it lets you set a new one from the sign-in screen. See [Forgot your password?](#forgot-your-password)

## Adding printers

**LayerHound looks for printers on its own:** right after first-run setup, and then once a day. Printers it finds show up as **"printers found on your network"** on the Dashboard and Print Farm pages:
- **Klipper:** press **Add**.
- **Bambu Lab:** type the printer's 8-character access code (on its screen, under the network or WLAN settings) and press **Add**.
- **OctoPrint:** press **Allow in OctoPrint**, then click **Allow** in OctoPrint. No API key to copy.
- **Not yours?** Press **×** and it won't be suggested again. On a shared network, like a makerspace, the scan can find other people's printers too.

You can also add a printer by hand with **Print Farm → Add printer**, or scan any time with **Scan again** or **Network → Scan network**. In **Settings → Printer discovery** you can turn the daily scan off, or let LayerHound add Klipper printers without asking.

| Printer | What to enter |
|---|---|
| **Klipper** (Snapmaker U1, Creality K-series, Elegoo Neptune 4, Voron and others) | The printer's address, usually `http://PRINTER-IP:7125`. Some, like the Elegoo Neptune 4, use port 80: just `http://PRINTER-IP`. |
| **Bambu Lab** (P1, X1, A1 series) | The printer's IP address, **serial number** and 8-character **access code**, all on the printer's screen under the network or WLAN settings. |
| **OctoPrint** | The address (usually `http://PRINTER-IP:5000`) and an API key from OctoPrint → Settings → Application Keys. |

Tips:
- **Give printers fixed IP addresses** (a "DHCP reservation" in your router), so they don't move around.
- **Bambu printers allow only one local connection.** If LayerHound shows a Bambu printer offline, close any other tool watching it over your network.
- **Newer Bambu firmware** may need **LAN Only mode**, and on some models **Developer mode**, before tools like LayerHound can connect. See Bambu Lab's own instructions for your model.
- **Cameras:** Bambu P1 and A1 cameras, and Klipper cameras, are found automatically. For any other camera, add its snapshot or stream address as the printer's **Camera URL**.
- **Arrange the cards** to match your bench: **Print Farm → Reorder**.

LayerHound only **watches** your printers. It never starts, stops or changes prints.

## Around the dashboard

| Page | What it's for |
|---|---|
| **Dashboard** | Everything at a glance: printers, server health, services and alerts. |
| **Print Farm** | All printers in detail. Click one for its job, temperatures, camera and layer count. |
| **History** | Every print, with how it ended and how long it took, plus success rate and hours printed. |
| **Server** | The board itself: processor, memory, temperature, fan, storage, network. |
| **Storage** | Drive health and space, and a shared **LayerHound Files** folder for uploads and downloads. |
| **Network** | Internet health, devices you monitor, Wi-Fi settings and the network scan. |
| **Services** | Quick links and health checks for your other home-lab apps, plus Home Assistant and Pi-hole stats. |
| **Settings** | Farm name, colors, light or dark mode, alerts, fan, accounts, backups and updates. |

**Light or dark:** use the moon, sun and screen buttons under the logo. Each device remembers its own choice.

**Cooling fan:** on the LayerHound board, the fan runs quietly when the board is cool and speeds up as it warms. Adjust it in **Settings → Cooling fan**.

## Accounts and who can see what

All of this is in **Settings → Login & users**:

- **Admin:** can change anything.
- **View only:** can look at everything, but can't change anything. Good for staff.
- **Viewing without signing in:** for a wall screen in your shop. Turn on **Let anyone on my network view without signing in**. Changes still need an admin, and devices outside your network still need to sign in.
- **Access keys:** for gadgets such as an LED status bar. They can read but never change anything, and you can revoke them any time.

## Wi-Fi and the setup hotspot

- **Change Wi-Fi:** **Network → Wi-Fi**.
- **Setup hotspot** (**Settings → Setup hotspot**): **Auto** turns it on for small boards and off for PCs and laptops, so a laptop never turns its Wi-Fi into a hotspot. You can also choose **On** or **Off**.
- **When the board can't reach any network for a few minutes:** it starts the **LayerHound-Setup** Wi-Fi network so you can reconnect it from your phone. If LayerHound is already set up, you'll be asked to sign in as an admin first. The hotspot turns itself off once the board is back online.

## Updates

LayerHound checks for a new version once a day.

1. When one is available, **Settings → Updates** shows what's new.
2. Press **Update now**. LayerHound backs up its database, installs the update and restarts. That takes a minute or two, and your printers keep printing.
3. **If the new version doesn't start, the previous one comes back by itself.**
4. Open dashboards then show a **Reload** button to switch to the new version.

Only updates signed by Team Tactical RC are installed. You can turn off the daily check in the same place.

**Automatic updates (optional, off by default).** Turn on **Install updates automatically** in Settings → Updates and pick a time, for example 3:00 AM. The time is in your own time zone, taken from the browser you set it in. Once a day at that time, LayerHound installs a new version by itself, with the same backup and automatic rollback as Update now. A version that didn't work isn't tried again automatically, and an update that needs a full install waits for you. Settings → Updates shows when it last updated itself. Not available in Docker, where updates come from pulling the new image.

## Backups

**Settings → Data & backups → Download backup** saves your printers, monitored devices, services and settings to a file. **Restore** loads one back, for example onto a new board.

- If you include access codes and tokens, keep the backup file private.
- Print history and the files in LayerHound Files aren't included.

## Using LayerHound away from home

**Never open LayerHound to the internet** with port forwarding on your router. Use **Settings → Remote access** instead. It uses **[Tailscale](https://tailscale.com)**, a private network for your own devices that's free for personal use.

1. In **Settings → Remote access**, press **Connect with Tailscale**.
2. Sign in to Tailscale, or create a free account, on the page that opens. You can also scan the code to do it on your phone.
3. Settings shows **Connected** and your remote address, like `http://layerhound.your-tailnet.ts.net`.
4. Install the **Tailscale** app on your phone or laptop and sign in with the **same account**.
5. Open the remote address, or scan its code, and bookmark it. It works from anywhere, as if you were home.

- **Keep it connected:** Tailscale asks devices to sign in again every few months. To stop that for the board, open the [Tailscale admin console](https://login.tailscale.com/admin/machines), choose the board and pick **Disable key expiry**.
- **Turn off remote access** pauses it; turning it back on doesn't need a sign-in. **Sign out of Tailscale** removes the board from your account.
- Only devices signed in to your Tailscale account can reach the board. You still sign in to LayerHound as usual.
- **Docker or your own Linux machine:** install Tailscale on that machine yourself, the usual way. Settings → Remote access is for the LayerHound board.

## Forgot your password?

**With your recovery key:** on the sign-in screen, choose **Forgot your password?**, then enter your admin username, your recovery key and a new password. You're signed straight in, and LayerHound gives you a new recovery key to save; the old one stops working.

- **Your recovery key** is shown once, at the end of first-run setup. Write it in the box on the printed setup guide, or keep it in a password manager. Keep it private: with it, someone could sign in as admin.
- **Lost it, or set up LayerHound before recovery keys existed?** Make a new one in **Settings → Login & users → Recovery key** (it asks for your password). Making a new key stops the old one working.
- **View-only accounts** don't use recovery keys: an admin sets a new password for them in **Settings → Login & users**.

**Without a recovery key:** on the board (over SSH, or with a keyboard and screen attached), run:

```bash
layerhound reset-password
```

It asks for a new password, and signs that account out everywhere. `layerhound users` lists the accounts.

## Troubleshooting

**http://layerhound.local doesn't open**
- Make sure your phone or computer is on the same network as the board.
- Some Android phones and Windows PCs don't support `.local` names. Find the board's IP address in your router's list of devices (look for "layerhound") and open `http://THAT-IP` instead.
- Wait a minute after plugging the board in; it takes a little while to start.

**A printer shows offline**
- Check the printer is on and on the same network, and that its IP address hasn't changed.
- Bambu: close other tools connected to it locally, and check the access code. It changes if you reset the printer's network settings.
- Klipper: try the address with `:7125` and without a port.

**The dashboard looks out of date after an update**
- Press **Reload** on the banner, or refresh the page.

**Unplugging the board**
- Use **Settings → About & maintenance → Shut down board** first, then unplug once the activity light stops blinking. Pulling the power while LayerHound is writing can damage the SD card.

**Something else**
- **Settings → About & maintenance → Restart dashboard** fixes most temporary problems.
- Then tell us, using **Send feedback**.

## Feedback and help

Use **Send feedback** in the menu for ideas, problems or questions. It goes straight to Team Tactical RC, only when you press Send. It includes your message, the LayerHound version, and basic system details you can see and switch off. Add your email if you'd like a reply.

## Good to know

- **Usage stats are your choice.** First-run setup asks whether to send anonymous stats once a day (install count, printer counts by type, country, version). Nothing is sent unless you say yes; **Settings → Usage stats** shows exactly what's sent and lets you change your mind.
- **Your data stays home.** Printer access codes, passwords and history stay on your board. Access codes and tokens are stored encrypted. The only outside connections are internet-health checks, the daily update check, Tailscale if you turn on remote access, and anything you send yourself; see the [privacy details](../README.md#privacy-and-security).
- **LayerHound is not affiliated with** Bambu Lab, Klipper, Moonraker, OctoPrint, Creality, Elegoo, Snapmaker, Radxa or Raspberry Pi. Their names are used only to say what LayerHound works with.
- **Bambu Lab support may change.** Bambu has been limiting third-party access in firmware updates. A future Bambu firmware could stop LayerHound from reading Bambu printers; we'll adapt where we can.
- **License:** LayerHound is open source under the GNU AGPL v3. The LayerHound name, logo and mascot belong to Team Tactical RC ([details](../TRADEMARKS.md)).
