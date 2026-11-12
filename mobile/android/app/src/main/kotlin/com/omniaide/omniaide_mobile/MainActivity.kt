package com.omniaide.omniaide_mobile

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    private var overlayChannel: MethodChannel? = null
    private var pendingQuickCapture = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleOverlayIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleOverlayIntent(intent)
    }

    private fun handleOverlayIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(OverlayService.EXTRA_QUICK_CAPTURE, false) != true) {
            return
        }
        intent.removeExtra(OverlayService.EXTRA_QUICK_CAPTURE)
        val channel = overlayChannel
        if (channel != null) {
            channel.invokeMethod("quickCapture", null)
        } else {
            pendingQuickCapture = true
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "omniaide/clipboard"
        ).setMethodCallHandler { call, result ->
            if (call.method != "readImage") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            try {
                val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val clip = manager.primaryClip
                if (clip == null || clip.itemCount == 0) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val uri = clip.getItemAt(0).uri
                if (uri == null) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val mime = contentResolver.getType(uri) ?: "image/png"
                if (!mime.startsWith("image/")) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes == null || bytes.isEmpty()) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                result.success(
                    mapOf(
                        "bytes" to bytes,
                        "mime" to mime,
                        "name" to "clipboard"
                    )
                )
            } catch (e: Exception) {
                result.error("clipboard_failed", e.message, null)
            }
        }

        val overlay = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "omniaide/overlay"
        )
        overlayChannel = overlay
        overlay.setMethodCallHandler { call, result ->
            when (call.method) {
                "hasPermission" -> {
                    result.success(canDrawOverlays())
                }
                "requestPermission" -> {
                    try {
                        startActivity(
                            Intent(
                                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                Uri.parse("package:$packageName")
                            )
                        )
                    } catch (_: Exception) {
                    }
                    result.success(false)
                }
                "start" -> {
                    if (!canDrawOverlays()) {
                        result.success(false)
                        return@setMethodCallHandler
                    }
                    val label = call.argument<String>("label") ?: "随手记"
                    val state = call.argument<String>("state") ?: "idle"
                    startOverlayService(this, label, state)
                    result.success(true)
                }
                "update" -> {
                    val label = call.argument<String>("label") ?: "随手记"
                    val state = call.argument<String>("state") ?: "idle"
                    updateOverlayService(this, label, state)
                    result.success(true)
                }
                "stop" -> {
                    stopOverlayService(this)
                    result.success(true)
                }
                "isActive" -> {
                    result.success(OverlayService.isRunning)
                }
                else -> result.notImplemented()
            }
        }
        if (pendingQuickCapture) {
            pendingQuickCapture = false
            overlay.invokeMethod("quickCapture", null)
        }
    }

    private fun canDrawOverlays(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)
}
