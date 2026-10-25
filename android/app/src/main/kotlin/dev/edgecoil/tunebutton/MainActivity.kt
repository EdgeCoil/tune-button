// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
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
import org.json.JSONObject

/** Setup and diagnostics: Spotify sign-in, playlist, pairing, background-running checks, event log. */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var spotify: Spotify
    private val main = Handler(Looper.getMainLooper())
    private lateinit var root: LinearLayout
    private var pairer: Pairer? = null
    private var pairStatus: String? = null
    private var showSetup = false
    private var showAllLog = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        spotify = Spotify(store)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(24), dp(16), dp(24)) }
        // fitsSystemWindows: Android 15 draws apps edge to edge, under the status bar.
        setContentView(ScrollView(this).apply { fitsSystemWindows = true; addView(root) })
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
        val problems = backgroundProblems()
        val ready = spotify.signedIn() && spotify.canControlPlayback() && store.device != null && problems.isEmpty()

        hint(listOf(
            (if (spotify.signedIn()) "✓" else "✗") + " Spotify",
            (if (store.device != null) "✓" else "✗") + " Paired",
            (if (problems.isEmpty()) "✓" else "✗") + " Listening",
        ).joinToString("    "))
        pairStatus?.let { text(it) }
        if (store.device != null && settingsPending()) {
            banner("The button doesn't have your hold and double-press settings yet. Hold keys 1 and 2 for 3 s " +
                "(one-button build: hold it 5 s) until the LED flickers, then tap below.",
                if (pairer == null) "Send key settings" else "Cancel") { pair(false) }
        }

        section("Keys")
        hint("Tap a key to choose what it does when pressed, held or double-pressed.")
        keyGrid()

        if (!ready || showSetup) setup(problems)
        if (ready) button(if (showSetup) "Hide setup" else "Setup and permissions") { showSetup = !showSetup; render() }

        section("Recent presses")
        val fmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
        val entries = store.logEntries()
        if (entries.isEmpty()) hint("Nothing yet")
        for (e in if (showAllLog) entries else entries.take(5)) logRow(e, fmt)
        row(
            if (entries.size > 5) "Show " + (if (showAllLog) "fewer" else "all ${entries.size}") to { showAllLog = !showAllLog; render() } else null,
            "Refresh" to { render() },
            "Clear" to { store.clearLog(); render() },
        )
    }

    /** Spotify, pairing and background-running setup. Folded away once all of it is done. */
    private fun setup(problems: List<String>) {
        section("Spotify")
        hint("Create an app at developer.spotify.com (Web API), add the redirect URI ${Spotify.REDIRECT_URI}, and paste its client ID here.")
        val id = EditText(this).apply {
            setText(store.clientId); hint = "Client ID"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        root.addView(id)
        val signIn = {
            store.clientId = id.text.toString()
            try { startActivity(Intent(Intent.ACTION_VIEW, spotify.authorizeUri())) }
            catch (e: Exception) { toastDialog("Can't sign in", e.message ?: "") }
        }
        if (spotify.signedIn()) {
            text("✓ Signed in")
            if (!spotify.canControlPlayback()) {
                text("✗ Sign in again to allow playback control (play/pause, skip, volume…)")
                button("Sign in again") { signIn() }
            }
            button("Sign out") { spotify.signOut(); render() }
        } else {
            button("Sign in to Spotify") { signIn() }
        }

        section("Device")
        text(store.device?.let { "Paired: device ${hex(it.id)} · last press #${store.lastCounter}" } ?: "Not paired")
        hint("Hold keys 1 and 2 for 3 s until the LED flickers (one-button build: hold it 5 s), then tap Pair.")
        button(if (pairer == null) "Pair" else "Cancel") { pair(true) }

        section("Keep listening in the background")
        if (problems.isEmpty()) text("✓ Permissions granted, battery unrestricted, scan registered")
        problems.forEach { text("✗ $it") }
        button("Grant permissions") { requestPermissionsNeeded() }
        button("Allow unrestricted battery") {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        }
        hint("Samsung: also Settings → Battery → Background usage limits → make sure tune-button is not in Sleeping or Deep sleeping apps, and add it to Never sleeping apps.")
        button("Scan mode: ${scanModeName(store.scanMode)}") { chooseScanMode() }
    }

    /** The four keys as they sit on the board: 1 2 on top, 3 4 below. */
    private fun keyGrid() {
        for (r in 0..1) {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (c in 0..1) {
                val k = r * 2 + c + 1
                line.addView(keyCard(k), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                    setMargins(dp(4), dp(4), dp(4), dp(4))
                })
            }
            root.addView(line)
        }
    }

    private fun keyCard(k: Int): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(12), dp(14), dp(14))
        background = GradientDrawable().apply { cornerRadius = dp(16).toFloat(); setColor(CARD) }
        foreground = obtainStyledAttributes(intArrayOf(android.R.attr.selectableItemBackground)).run {
            getDrawable(0).also { recycle() }
        }
        isClickable = true
        setOnClickListener { keySheet(k) }
        addView(TextView(context).apply { text = "$k"; textSize = 26f; typeface = Typeface.DEFAULT_BOLD; setTextColor(ACCENT) })
        addView(TextView(context).apply { text = store.slot(k, Packet.PRESS).short(); textSize = 15f; setPadding(0, dp(4), 0, 0) })
        for (g in listOf(Packet.HOLD, Packet.DOUBLE)) {
            val a = store.slot(k, g)
            if (a.type == Action.Type.NONE) continue
            addView(TextView(context).apply {
                text = "${gestureTitle(g)}: ${a.short()}"; textSize = 13f; setTextColor(MUTED); setPadding(0, dp(4), 0, 0)
            })
        }
    }

    private fun keySheet(k: Int) {
        val gestures = listOf(Packet.PRESS, Packet.HOLD, Packet.DOUBLE)
        val items = gestures.map { "${gestureTitle(it)}:  ${store.slot(k, it).describe()}" } + "Try the press now"
        AlertDialog.Builder(this).setTitle("Key $k · ${KEY_PLACES[k - 1]}")
            .setItems(items.toTypedArray()) { _, i -> if (i < 3) chooseAction(k, gestures[i]) else runNow(k) }
            .setNegativeButton("Done", null)
            .show()
    }

    private fun gestureTitle(g: Int) = when (g) { Packet.HOLD -> "Hold"; Packet.DOUBLE -> "Double press"; else -> "Press" }

    private fun logRow(e: JSONObject, fmt: SimpleDateFormat) {
        val t = fmt.format(Date(e.optLong("t")))
        if (e.optString("kind") != "press") return hint("$t  ${e.optString("kind")} ${e.optInt("code")}")
        val what = if (e.has("key")) "Key ${e.optInt("key")} ${e.optString("gesture")}" else e.optString("button")
        text("${if (e.optBoolean("ok")) "✓" else "✗"}  $t  $what · ${e.optString("result")}")
        hint(listOfNotNull(
            "#${e.optLong("counter")}",
            e.optInt("age_ms").takeIf { it >= 0 }?.let { "heard ${it / 1000.0} s" },
            "Spotify ${e.optLong("api_ms")} ms",
            e.optInt("battery").takeIf { it >= 0 }?.let { "battery $it%" },
        ).joinToString(" · "), indent = true)
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

    /** The button needs a settings write: its settings differ from what the slots ask for. */
    private fun settingsPending(): Boolean {
        val want = store.wantedSettings
        // -1: never written (older firmware, or paired before four keys), which behaves as 0.
        return want != store.deviceSettings && !(want == 0 && store.deviceSettings == -1)
    }

    private fun pair(pairing: Boolean) {
        pairer?.let { it.cancel(); return }
        if (Build.VERSION.SDK_INT >= 31 && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED ||
            !Scanner.canScan(this)) {
            requestPermissionsNeeded(); return
        }
        pairer = Pairer(this, pairing) { msg, done ->
            main.post {
                pairStatus = msg
                if (done) pairer = null
                render()
            }
        }.also { it.start() }
        render()
    }

    private fun chooseAction(key: Int, gesture: Int) {
        val types = Action.Type.values()
        AlertDialog.Builder(this).setTitle("Key $key · ${gestureTitle(gesture)}")
            .setItems(types.map { it.label }.toTypedArray()) { _, i ->
                val t = types[i]
                when {
                    t.needsPlaylist -> choosePlaylist(t) { id, name -> store.setSlot(key, gesture, Action(t, id, name)); render() }
                    t == Action.Type.WEBHOOK -> chooseUrl(store.slot(key, gesture).url) { url -> store.setSlot(key, gesture, Action(t, url = url)); render() }
                    else -> { store.setSlot(key, gesture, Action(t)); render() }
                }
            }.show()
    }

    private fun chooseUrl(current: String?, done: (String) -> Unit) {
        val field = EditText(this).apply {
            setText(current ?: ""); hint = "https://…/api/webhook/…"; inputType = InputType.TYPE_TEXT_VARIATION_URI
        }
        AlertDialog.Builder(this).setTitle("Webhook URL")
            .setMessage("Gets a POST with JSON: key, gesture, and the song's uri, title and artist when one is playing.")
            .setView(field)
            .setPositiveButton("Save") { _, _ ->
                val url = field.text.toString().trim()
                if (url.startsWith("https://") || url.startsWith("http://")) done(url)
                else toastDialog("Not a URL", "It should start with https:// (or http:// on your own network)")
            }
            .setNegativeButton("Cancel", null).show()
    }

    /** Playlists the user can change for ADD/REMOVE; any of theirs for PLAY_PLAYLIST. */
    private fun choosePlaylist(type: Action.Type, done: (id: String, name: String) -> Unit) {
        thread {
            try {
                val lists = spotify.playlists(all = type == Action.Type.PLAY_PLAYLIST)
                main.post {
                    AlertDialog.Builder(this).setTitle(type.label)
                        .setItems(lists.map { it.name }.toTypedArray()) { _, i -> done(lists[i].id, lists[i].name) }
                        .show()
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

    private fun runNow(key: Int) {
        WorkManager.getInstance(this).enqueue(
            OneTimeWorkRequestBuilder<PressWorker>().setInputData(workDataOf(
                "key" to key, "gesture" to Packet.PRESS, "counter" to -1L, "age_ms" to -1,
            )).build(),
        )
        main.postDelayed({ render() }, 3000)
    }

    // ------------------------------------------------------------------ view helpers

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun title(s: String) = root.addView(TextView(this).apply { text = s; textSize = 26f; typeface = Typeface.DEFAULT_BOLD })
    private fun section(s: String) = root.addView(TextView(this).apply {
        text = s; textSize = 18f; typeface = Typeface.DEFAULT_BOLD; setPadding(0, dp(24), 0, dp(6))
    })
    private fun text(s: String) = root.addView(TextView(this).apply { text = s; textSize = 14f; setPadding(0, dp(3), 0, dp(1)) })
    private fun hint(s: String, indent: Boolean = false) = root.addView(TextView(this).apply {
        text = s; textSize = 13f; setTextColor(MUTED); setPadding(if (indent) dp(22) else 0, dp(2), 0, dp(2))
    })
    private fun button(s: String, onClick: (View) -> Unit) = root.addView(Button(this).apply { text = s; setOnClickListener(onClick) })

    /** Borderless buttons side by side; null entries are skipped. */
    private fun row(vararg items: Pair<String, () -> Unit>?) = root.addView(LinearLayout(this).apply {
        for (item in items.filterNotNull()) addView(Button(context, null, android.R.attr.borderlessButtonStyle).apply {
            text = item.first; setOnClickListener { item.second() }
        })
    })

    private fun banner(msg: String, action: String, onClick: (View) -> Unit) = root.addView(LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(12), dp(14), dp(6))
        background = GradientDrawable().apply { cornerRadius = dp(12).toFloat(); setColor(WARN) }
        addView(TextView(context).apply { text = msg; textSize = 14f })
        addView(Button(context, null, android.R.attr.borderlessButtonStyle).apply { text = action; setOnClickListener(onClick) })
    }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
        topMargin = dp(12)
    })

    private fun toastDialog(t: String, m: String) = AlertDialog.Builder(this).setTitle(t).setMessage(m).setPositiveButton("OK", null).show()
    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    companion object {
        private val KEY_PLACES = listOf("top left", "top right", "bottom left", "bottom right")
        private const val CARD = 0xFFF1F3F4.toInt()
        private const val WARN = 0xFFFFF2CC.toInt()
        private const val MUTED = 0xFF5F6368.toInt()
        private const val ACCENT = 0xFF1E8E3E.toInt()
    }
}
