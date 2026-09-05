# PawTrack

Self-hosted pet tracking over a [Meshtastic](https://meshtastic.org) LoRa mesh — live GPS position, geofences with enter/exit alerts, an offline-pet watchdog, camera viewing with PTZ control, and (coming soon) a companion Android app with background location sharing and push notifications. Multi-user, bilingual (Croatian/English), and built to run entirely on your own hardware.

> Status: web app is functional and in active use. The Android companion app and the first tagged release are in progress — see [Roadmap](#roadmap).

## Why this exists

Meshtastic T1000-E-style trackers are a cheap, subscription-free way to track a pet over LoRa instead of cellular GPS trackers that need a monthly plan and a phone signal where your pet actually is. This project turns a couple of home Meshtastic nodes (acting as gateways with WiFi + mesh admin rights over the tracker) into a full web app: live map, geofencing, alert history, and remote radio configuration — no more manually editing config files or using the CLI every time you want to tweak something.

It grew from a single-pet, single-user script into a generic, multi-tenant, multi-language app so anyone with Meshtastic hardware can self-host it for their own pet(s).

## Features

- **Live map** — every pet's current position, battery, and speed, updated in real time over a WebSocket.
- **Geofencing** — draw a circle or polygon per pet on the map; get an alert (web + Telegram) when they leave or come back, with consecutive-reading confirmation so GPS jitter near a fence edge doesn't cause false alarms.
- **Movement timeline** — scrub back through a pet's position history (last hour to last 7 days) with a map trail and per-fix detail list.
- **Remote radio config** — push channel/PSK, GPS interval, power-saving, and buzzer settings to a tracker over the mesh itself (Meshtastic's AdminMessage protocol) — no direct connection to the tracker needed.
- **"Ring" / find-my-pet** — send a command that makes a T1000-E-class tracker beep loudly, for physical search and recovery.
- **Multiple gateways, channels, and pets** — not tied to one node or one animal; add as many of each as your mesh has.
- **Camera viewer with PTZ** — add any RTSP camera by URL, watch it over HLS in the browser, and pan/tilt/zoom + save preset positions for ONVIF-capable PTZ cameras.
- **Multi-user with an admin role** — every user manages their own gateways/pets/cameras in isolation; the first account created becomes an admin, who can additionally see every user's last known phone location *and* the distance from their own pets to their people — useful if you're the person other household members' pet-location-sharing "checks in" with.
- **Bilingual UI** — Croatian and English, switchable anytime, with the setting remembered per browser.
- **Self-hosted** — SQLite, no cloud dependency, one `install.sh` away from running on your own Debian/Ubuntu server.

## Architecture

- **Backend:** Python 3.11+, FastAPI + Uvicorn, SQLModel/SQLite, a WebSocket for live push to the browser, and the [`meshtastic`](https://pypi.org/project/meshtastic/) Python library talking to each gateway node over its WiFi TCP API (port 4403).
- **Frontend:** vanilla JavaScript (ES modules, no build step), [Leaflet](https://leafletjs.com/) + Leaflet.draw for the map/geofence editor, [hls.js](https://github.com/video-dev/hls.js) for camera playback.
- **Cameras:** [mediamtx](https://github.com/bluenviron/mediamtx) remuxes each camera's RTSP feed to HLS on demand; the backend keeps its path config in sync with your camera list live, over mediamtx's own control API — no manual YAML editing.

```
Meshtastic tracker (e.g. T1000-E)
        │ LoRa mesh (private channel)
        ▼
Gateway node(s) (any Meshtastic node with WiFi enabled)
        │ TCP API (port 4403)
        ▼
PawTrack backend (FastAPI) ── SQLite
        │ WebSocket
        ▼
PawTrack web app (browser) / Android companion app
```

## Requirements

- One or more Meshtastic nodes with WiFi enabled, reachable from the server on your LAN, set up as mesh admins over the node(s) you want to track (see [Meshtastic's admin channel docs](https://meshtastic.org/docs/configuration/remote-admin/)).
- A private Meshtastic channel that broadcasts position from the tracker (`position_precision` > 0 on that channel).
- A Debian/Ubuntu server (physical box, VM, or LXC container) on the same network as your gateway nodes, with Python 3.11+.
- Optional: an RTSP-capable camera for the camera viewer; a Telegram bot token + chat ID for Telegram alerts (`@BotFather` on Telegram, a few minutes to set up).

**A note on hardware limits:** Meshtastic's WiFi TCP API only accepts one client connection at a time per node. Since PawTrack holds a persistent connection to each gateway 24/7, you generally can't *also* use the official Meshtastic phone app/CLI against the same gateway node at the same time — disable the gateway in PawTrack's Devices view first if you need direct access, or dedicate a node purely as a PawTrack gateway.

## Installation

```bash
git clone https://github.com/<your-username>/pet-tracking-meshtastic.git
cd pet-tracking-meshtastic
sudo ./install.sh
```

The installer will:
1. Install Python, nginx, and (optionally) mediamtx for camera support.
2. Create a `pawtrack` system user and install the app under `/opt/pawtrack`.
3. Generate a random session secret key.
4. Set up and start `pawtrack.service` (and `pawtrack-mediamtx.service` if cameras are enabled) via systemd.
5. Configure nginx as a reverse proxy on port 80 (optional — skip this if you're fronting it with your own reverse proxy, e.g. a Cloudflare Tunnel).

Then open `http://<your-server>/` and **register the first account** — it automatically becomes the admin. Everyone who registers after that is a regular user managing their own gateways/pets/cameras.

Re-running `sudo ./install.sh` on an existing install pulls in code changes and restarts the service without touching your database, `.env`, or mediamtx config.

### First-time setup checklist

1. **Devices → Gateway nodes**: add each Meshtastic node's IP address.
2. **Channels**: add the private channel your tracker broadcasts position on (name, device slot index, PSK — leave PSK blank to auto-generate one, or paste in an existing channel's PSK to reuse it), then use **Push to devices** to write it to your gateway(s) and tracker.
3. **Devices → Pets**: add a pet, optionally discovering its node ID from a connected gateway's known-node list (or add the pet first and assign the node ID later — it's optional).
4. **Geofences**: draw a circle or polygon around the pet's usual safe area.
5. **Settings**: add your Telegram bot token + chat ID if you want alerts there too, and change your password from whatever you picked at registration.
6. If you're the admin and want cross-user visibility, that's automatic — the **Admin** nav item shows every user's last shared phone location and pet positions once the (forthcoming) Android app starts reporting them.

### Reverse-proxying it yourself

If you skip the nginx step (e.g. you're using Cloudflare Tunnel with Zero Trust / Access for authentication in front of this), see `deploy/nginx-pawtrack.conf` for the two things any proxy in front of PawTrack needs: forwarding `/ws` with WebSocket upgrade headers, and (if you're behind a caching CDN) disabling caching so frontend updates aren't served stale.

## Versions

| Component | Version |
|---|---|
| PawTrack web app | `0.1.0` (pre-release) |
| PawTrack Android app | not yet released |

Releases are published under [Releases](../../releases) once tagged.

## Roadmap

- [ ] Android companion app (installable APK under Releases): point it at your PawTrack URL (including a Cloudflare Zero Trust / Access-protected domain), sign in, see the same live map, and — the point of it — share your own phone's location in the background so the admin dashboard has both halves of the "how far is my pet from me" picture. Push notifications instead of/alongside Telegram.
- [ ] Tagged `v1.0.0` release of both the web app and the Android app.

## Contributing / issues

This started as a personal project and is shared as-is for anyone with similar hardware. Issues and PRs are welcome.

## License

MIT — see [LICENSE](LICENSE).
