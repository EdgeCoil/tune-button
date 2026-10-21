// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.concurrent.thread

/** Setup and diagnostics: Spotify sign-in, playlist, pairing, background-running checks, event log. */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var spotify: Spotify
    private val main = Handler(Looper.getMainLooper())
    private lateinit var root: LinearLayout
    private var pairer: Pairer? = null
    private var pairStatus: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        spotify = Spotify(store)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(24), dp(16), dp(24)) }
        setContentView(ScrollView(this).apply { addView(root) })
        handleRedirect(intent)
        render()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleRedirect(intent)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        // Android 10–11: background location must be asked for on its own, after foreground location.
        if (Build.VERSION.SDK_INT in 29..30 && Manifest.permission.ACCESS_FINE_LOCATION in permissions &&
            checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION), 2)
        }
        Scanner.register(this)
        render()
    }

    private fun handleRedirect(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme != "tunebutton") return
        setIntent(Intent())
        thread {
            val err = try { spotify.completeAuthorization(uri) } catch (e: Exception) { e.message }
            main.post { if (err != null) toastDialog("Sign-in failed", err); render() }
        }
    }

    // ------------------------------------------------------------------ UI

    private fun render() {
        root.removeAllViews()
        title("tune-button")

        section("1 · Spotify")
        text("Create an app at developer.spotify.com (Web API), add the redirect URI ${Spotify.REDIRECT_URI}, and paste its client ID here.")
        val id = EditText(this).apply {
            setText(store.clientId); hint = "Client ID"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        root.addView(id)
        if (spotify.signedIn()) {
            text("✓ Signed in")
            button("Sign out") { spotify.signOut(); render() }
        } else {
            button("Sign in to Spotify") {
                store.clientId = id.text.toString()
                try { startActivity(Intent(Intent.ACTION_VIEW, spotify.authorizeUri())) }
                catch (e: Exception) { toastDialog("Can't sign in", e.message ?: "") }
            }
        }

        section("2 · Playlist for the second button")
        text(store.playlistName?.let { "Adds to: $it" } ?: "No playlist chosen")
        button("Choose playlist") { choosePlaylist() }

        section("3 · Device")
        text(store.device?.let { "Paired: device ${hex(it.id)} · last press #${store.lastCounter}" } ?: "Not paired")
        pairStatus?.let { text(it) }
        button(if (pairer == null) "Pair (first hold both buttons 3 s, or one button 5 s)" else "Cancel pairing") { pair() }

        section("4 · Keep listening in the background")
        val problems = backgroundProblems()
        if (problems.isEmpty()) text("✓ Permissions granted, battery unrestricted, scan registered")
        problems.forEach { text("✗ $it") }
        button("Grant permissions") { requestPermissionsNeeded() }
        button("Allow unrestricted battery") {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        }
        text("Samsung: also Settings → Battery → Background usage limits → make sure tune-button is not in Sleeping or Deep sleeping apps, and add it to Never sleeping apps.")
        button("Scan mode: ${scanModeName(store.scanMode)}") { chooseScanMode() }

        section("Test without the device")
        button("Like current song now") { runNow(Packet.LIKE) }
        button("Add current song to playlist now") { runNow(Packet.PLAYLIST) }

        section("Recent presses")
        text("‘heard’ is how long after the press the phone first heard it, measured by the device.")
        val fmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
        val entries = store.logEntries()
        if (entries.isEmpty()) text("Nothing yet")
        for (e in entries) {
            val t = fmt.format(Date(e.optLong("t")))
            text(when (e.optString("kind")) {
                "press" -> "$t  #${e.optLong("counter")} ${e.optString("button")}  " +
                    (if (e.optInt("age_ms") >= 0) "heard ${e.optInt("age_ms") / 1000.0}s  " else "") +
                    "api ${e.optLong("api_ms")}ms  " +
                    (if (e.optInt("battery") >= 0) "bat ${e.optInt("battery")}%  " else "") +
                    "${if (e.optBoolean("ok")) "✓" else "✗"} ${e.optString("result")}"
                else -> "$t  ${e.optString("kind")} ${e.optInt("code")}"
            })
        }
        button("Refresh") { render() }
        button("Clear log") { store.clearLog(); render() }
    }

    private fun backgroundProblems(): List<String> {
        val out = mutableListOf<String>()
        if (store.device == null) return listOf("Pair the device first")
        if (!Scanner.canScan(this)) out += "Bluetooth scan permission"
        if (Build.VERSION.SDK_INT in 29..30 &&
            checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED)
            out += "Location: Allow all the time (Android 10–11 need it for background scans)"
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            out += "Notifications (how you know a press worked)"
        if (!getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName))
            out += "Battery: not unrestricted, so the system may stop delivering presses"
        Scanner.register(this)?.let { out += it }
        return out
    }

    private fun requestPermissionsNeeded() {
        val want = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= 31) want += listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else want += Manifest.permission.ACCESS_FINE_LOCATION
        if (Build.VERSION.SDK_INT >= 33) want += Manifest.permission.POST_NOTIFICATIONS
        requestPermissions(want.toTypedArray(), 1)
    }

    private fun pair() {
        pairer?.let { it.cancel(); return }
        if (Build.VERSION.SDK_INT >= 31 && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED ||
            !Scanner.canScan(this)) {
            requestPermissionsNeeded(); return
        }
        pairer = Pairer(this) { msg, done ->
            main.post {
                pairStatus = msg
                if (done) pairer = null
                render()
            }
        }.also { it.start() }
        render()
    }

    private fun choosePlaylist() {
        thread {
            try {
                val lists = spotify.writablePlaylists()
                main.post {
                    AlertDialog.Builder(this).setTitle("Add to which playlist?")
                        .setItems(lists.map { it.name }.toTypedArray()) { _, i ->
                            store.playlistId = lists[i].id; store.playlistName = lists[i].name; render()
                        }.show()
                }
            } catch (e: Exception) {
                main.post { toastDialog("Couldn't list playlists", e.message ?: e.toString()) }
            }
        }
    }

    private fun chooseScanMode() {
        val modes = intArrayOf(ScanSettings.SCAN_MODE_LOW_POWER, ScanSettings.SCAN_MODE_BALANCED, ScanSettings.SCAN_MODE_LOW_LATENCY)
        AlertDialog.Builder(this).setTitle("Background scan mode")
            .setItems(modes.map { scanModeName(it) }.toTypedArray()) { _, i ->
                store.scanMode = modes[i]; Scanner.register(this); render()
            }.show()
    }

    private fun scanModeName(m: Int) = when (m) {
        ScanSettings.SCAN_MODE_LOW_POWER -> "low power"
        ScanSettings.SCAN_MODE_LOW_LATENCY -> "low latency"
        else -> "balanced"
    }

    private fun runNow(button: Int) {
        WorkManager.getInstance(this).enqueue(
            OneTimeWorkRequestBuilder<PressWorker>().setInputData(workDataOf("button" to button, "counter" to -1L, "age_ms" to -1)).build(),
        )
        main.postDelayed({ render() }, 3000)
    }

    // ------------------------------------------------------------------ view helpers

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun title(s: String) = root.addView(TextView(this).apply { text = s; textSize = 24f })
    private fun section(s: String) = root.addView(TextView(this).apply {
        text = s; textSize = 18f; setPadding(0, dp(20), 0, dp(4))
    })
    private fun text(s: String) = root.addView(TextView(this).apply { text = s; textSize = 14f; setPadding(0, dp(2), 0, dp(2)) })
    private fun button(s: String, onClick: (View) -> Unit) = root.addView(Button(this).apply { text = s; setOnClickListener(onClick) })
    private fun toastDialog(t: String, m: String) = AlertDialog.Builder(this).setTitle(t).setMessage(m).setPositiveButton("OK", null).show()
    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
}
