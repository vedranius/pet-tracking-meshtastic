package com.pawtrack.app

import android.Manifest
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.BatteryManager
import android.os.IBinder
import android.os.Looper
import androidx.core.app.ActivityCompat
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Foreground service doing two independent jobs while the app is
 * backgrounded (or fully closed):
 *  1. Periodically read this device's location and POST it to
 *     /api/device-location, so an admin can see how far the user is from
 *     their pet(s).
 *  2. Keep a WebSocket open to /ws and turn incoming "alert" events into
 *     local notifications — this is what lets the app notify constantly
 *     without needing Firebase/a Google account, matching the rest of the
 *     project's self-hosted-only design.
 *
 * Both use the session cookie the user's WebView login already set (see
 * CookieBridge) rather than re-implementing auth here. */
class LocationShareService : Service() {

    private lateinit var prefs: PrefsRepository
    private var locationManager: LocationManager? = null
    private var lastLocation: Location? = null
    private val running = AtomicBoolean(false)
    private var heartbeatThread: Thread? = null

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // 0 = no timeout, needed to keep the WebSocket open
        .build()

    private var webSocket: WebSocket? = null
    private var wsReconnectAttempt = 0
    private val wsBackoffSeconds = intArrayOf(2, 5, 10, 20, 30, 60)
    private var wsReconnectThread: Thread? = null
    @Volatile private var wsShouldRun = false

    private val locationListener = object : LocationListener {
        override fun onLocationChanged(location: Location) {
            lastLocation = location
            postLocation(location)
        }
    }

    override fun onCreate() {
        super.onCreate()
        prefs = PrefsRepository(this)
        locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSharing()
            return START_NOT_STICKY
        }
        if (!hasLocationPermission()) {
            // Nothing useful this service can do without it, and starting a
            // foregroundServiceType="location" service without the
            // permission throws on newer Android versions.
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NotificationHelper.SHARING_NOTIFICATION_ID, NotificationHelper.buildSharingNotification(this))
        startSharing()
        return START_STICKY
    }

    private fun startSharing() {
        if (running.getAndSet(true)) return
        startLocationUpdates()
        startHeartbeat()
        connectWebSocket()
    }

    /** Only called from MainActivity's "change server" flow, when the
     * account itself is being switched — there's no user-facing on/off
     * control for sharing otherwise (see PrefsRepository). */
    private fun stopSharing() {
        running.set(false)
        try {
            locationManager?.removeUpdates(locationListener)
        } catch (e: SecurityException) {
            // permission was revoked underneath us — nothing left to clean up
        }
        heartbeatThread?.interrupt()
        wsShouldRun = false
        wsReconnectThread?.interrupt()
        webSocket?.close(1000, "stopping")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun hasLocationPermission(): Boolean {
        return ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    }

    private fun startLocationUpdates() {
        if (!hasLocationPermission()) return
        try {
            val provider = when {
                locationManager?.isProviderEnabled(LocationManager.GPS_PROVIDER) == true -> LocationManager.GPS_PROVIDER
                locationManager?.isProviderEnabled(LocationManager.NETWORK_PROVIDER) == true -> LocationManager.NETWORK_PROVIDER
                else -> null
            }
            if (provider != null) {
                locationManager?.requestLocationUpdates(provider, UPDATE_MIN_TIME_MS, UPDATE_MIN_DISTANCE_M, locationListener, Looper.getMainLooper())
                locationManager?.getLastKnownLocation(provider)?.let {
                    lastLocation = it
                    postLocation(it)
                }
            }
        } catch (e: SecurityException) {
            // permission revoked between the check above and the call — next
            // start of the service will re-check from scratch.
        }
    }

    /** GPS updates stop arriving entirely once the device is stationary, so
     * this re-posts the last known fix every minute regardless — otherwise
     * an admin watching "last seen" would see it go stale the moment
     * someone sits still, even though the app is still running fine. */
    private fun startHeartbeat() {
        heartbeatThread = Thread {
            while (running.get()) {
                try {
                    Thread.sleep(HEARTBEAT_INTERVAL_MS)
                    lastLocation?.let { postLocation(it) }
                } catch (e: InterruptedException) {
                    break
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun batteryPercent(): Int? {
        val bm = getSystemService(BATTERY_SERVICE) as? BatteryManager ?: return null
        val pct = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return if (pct in 0..100) pct else null
    }

    private fun postLocation(location: Location) {
        val baseUrl = prefs.serverUrl ?: return
        val cookie = CookieBridge.cookieHeaderFor(baseUrl) ?: return // not signed in yet — try again next cycle

        val body = JSONObject().apply {
            put("lat", location.latitude)
            put("lon", location.longitude)
            put("accuracy", location.accuracy.toDouble())
            batteryPercent()?.let { put("battery", it) }
        }
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/device-location")
            .header("Cookie", cookie)
            .post(body.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        httpClient.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { /* best-effort, retried next cycle */ }
            override fun onResponse(call: Call, response: Response) {
                response.close()
            }
        })
    }

    private fun connectWebSocket() {
        val baseUrl = prefs.serverUrl ?: return
        wsShouldRun = true
        openWebSocketOnce(baseUrl)
    }

    private fun openWebSocketOnce(baseUrl: String) {
        val wsUrl = baseUrl.trimEnd('/')
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://") + "/ws"
        val requestBuilder = Request.Builder().url(wsUrl)
        CookieBridge.cookieHeaderFor(baseUrl)?.let { requestBuilder.header("Cookie", it) }

        webSocket = httpClient.newWebSocket(requestBuilder.build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                wsReconnectAttempt = 0
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleWsMessage(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                scheduleReconnect(baseUrl)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (wsShouldRun) scheduleReconnect(baseUrl)
            }
        })
    }

    private fun scheduleReconnect(baseUrl: String) {
        if (!wsShouldRun) return
        val delaySeconds = wsBackoffSeconds[wsReconnectAttempt.coerceAtMost(wsBackoffSeconds.size - 1)]
        wsReconnectAttempt++
        wsReconnectThread = Thread {
            try {
                Thread.sleep(delaySeconds * 1000L)
                if (wsShouldRun) openWebSocketOnce(baseUrl)
            } catch (e: InterruptedException) {
                // stopping — no reconnect
            }
        }.apply { isDaemon = true; start() }
    }

    private fun handleWsMessage(text: String) {
        try {
            val json = JSONObject(text)
            if (json.optString("type") == "alert") {
                val eventType = json.optString("event_type")
                val message = json.optString("message")
                NotificationHelper.showAlert(this, eventType, EventText.render(this, eventType, message))
            }
        } catch (e: JSONException) {
            // not a message shape we care about
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        running.set(false)
        try {
            locationManager?.removeUpdates(locationListener)
        } catch (e: SecurityException) {
        }
        heartbeatThread?.interrupt()
        wsShouldRun = false
        wsReconnectThread?.interrupt()
        webSocket?.close(1000, "service destroyed")
    }

    companion object {
        const val ACTION_STOP = "com.pawtrack.app.action.STOP_SHARING"
        private const val UPDATE_MIN_TIME_MS = 30_000L
        private const val UPDATE_MIN_DISTANCE_M = 15f
        private const val HEARTBEAT_INTERVAL_MS = 60_000L
    }
}
