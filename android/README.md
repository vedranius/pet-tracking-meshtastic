# PawTrack Android app

A thin native shell around the PawTrack web app (so it looks and behaves exactly like the site you already use — including working through a Cloudflare Access / Zero Trust OTP login) plus two things a browser tab can't do reliably: background location sharing and always-on push-style notifications.

## How it works

- **WebView, not a rebuilt UI.** The main screen is a WebView pointed at the server URL you enter on first launch. Signing in, the dashboard, geofences, cameras — all of it is the same PawTrack frontend rendered exactly as in a browser. This is also why Cloudflare Access works out of the box: its login/OTP interstitial is just another page the WebView renders before redirecting back to your server.
- **Background location**, via a foreground service (`LocationShareService`) using Android's plain `LocationManager` (no Google Play Services dependency, so it also works on de-Googled/AOSP devices) — posts to `/api/device-location` every ~30s of movement or at least once a minute regardless, using the session cookie your WebView login already set.
- **Notifications without Firebase.** The same foreground service keeps a WebSocket open to `/ws` (the same endpoint the web dashboard uses) and turns `alert` events into local notifications — no Google account, no external push service, no cloud dependency beyond your own server, consistent with the rest of the project.
- **Onboarding** walks through granting location, background location, notification, and battery-optimization-exemption permissions before handing off to the WebView — all four matter for sharing to keep working once the app isn't in the foreground.

## Building locally

No Gradle wrapper is committed (it needs a binary jar this workflow can't generate), so install [Gradle 8.9](https://gradle.org/releases/) and a JDK 17 yourself, then:

```bash
cd android
gradle assembleDebug
```

The debug APK lands in `app/build/outputs/apk/debug/`. It's signed with the Android debug key, fine for testing on your own device but not for distributing.

## Releasing

CI (`.github/workflows/android.yml`) builds a signed release APK automatically on every push to `android/` and publishes it under [Releases](../../releases) when a tag like `android-v0.1.0` is pushed. It signs with a keystore stored as repo secrets (`PAWTRACK_KEYSTORE_B64`, `PAWTRACK_KEYSTORE_PASSWORD`, `PAWTRACK_KEY_ALIAS`, `PAWTRACK_KEY_PASSWORD`) so every release shares the same signing identity and installs as an upgrade over the last one. Without those secrets set, it falls back to debug signing (still builds, just not installable as an update path).

To cut a release:

```bash
git tag android-v0.1.0
git push origin android-v0.1.0
```
