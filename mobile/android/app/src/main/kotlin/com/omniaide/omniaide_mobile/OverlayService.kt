package com.omniaide.omniaide_mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import kotlin.math.abs

/**
 * System-wide floating status button for Android.
 *
 * The app runs on Android without an equivalent of iOS Live Activities, so a
 * small overlay (SYSTEM_ALERT_WINDOW) is used instead. It stays above other
 * apps, shows running/waiting state, and tapping it opens OmniAide (or quick
 * capture when idle).
 */
class OverlayService : Service() {
    companion object {
        private const val CHANNEL_ID = "omniaide_overlay"
        private const val NOTIFICATION_ID = 6101
        const val ACTION_START = "com.omniaide.omniaide_mobile.overlay.START"
        const val ACTION_UPDATE = "com.omniaide.omniaide_mobile.overlay.UPDATE"
        const val ACTION_STOP = "com.omniaide.omniaide_mobile.overlay.STOP"
        const val EXTRA_LABEL = "label"
        const val EXTRA_STATE = "state"
        const val EXTRA_QUICK_CAPTURE = "quick_capture"

        @Volatile
        var isRunning: Boolean = false
            private set
    }

    private var windowManager: WindowManager? = null
    private var overlayView: View? = null
    private var params: WindowManager.LayoutParams? = null
    private var labelView: TextView? = null
    private var indicator: TextView? = null
    private var spinner: ProgressBar? = null
    private var label = "随手记"
    private var state = "idle"

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startInForeground()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        isRunning = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        label = intent?.getStringExtra(EXTRA_LABEL) ?: label
        state = intent?.getStringExtra(EXTRA_STATE) ?: state
        if (!canDrawOverlays()) {
            stopSelf()
            return START_NOT_STICKY
        }
        ensureOverlay()
        applyState()
        updateNotification()
        return START_STICKY
    }

    override fun onDestroy() {
        overlayView?.let { view ->
            try {
                windowManager?.removeView(view)
            } catch (_: Exception) {
            }
        }
        overlayView = null
        isRunning = false
        super.onDestroy()
    }

    private fun canDrawOverlays(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "OmniAide 悬浮按钮",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "在其他 App 上显示任务状态和随手记入口"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun startInForeground() {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification())
    }

    private fun buildNotification(): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val openPending = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stopPending = PendingIntent.getService(
            this,
            1,
            Intent(this, OverlayService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("OmniAide")
            .setContentText("悬浮按钮运行中 · $label")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(openPending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(R.mipmap.ic_launcher, "关闭悬浮按钮", stopPending)
            .build()
    }

    private fun ensureOverlay() {
        if (overlayView != null) return
        val manager = windowManager ?: return

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(9), dp(14), dp(9))
            elevation = dp(8).toFloat()
        }
        val spinnerView = ProgressBar(this).apply {
            isIndeterminate = true
            visibility = View.GONE
            val size = dp(17)
            layoutParams = LinearLayout.LayoutParams(size, size)
        }
        val indicatorView = TextView(this).apply {
            textSize = 11f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            val size = dp(18)
            layoutParams = LinearLayout.LayoutParams(size, size)
        }
        val labelViewLocal = TextView(this).apply {
            textSize = 13f
            setTypeface(typeface, Typeface.BOLD)
            maxLines = 1
            setPadding(dp(5), 0, 0, 0)
        }
        root.addView(spinnerView)
        root.addView(indicatorView)
        root.addView(labelViewLocal)

        val layout = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            val prefs = getSharedPreferences("omniaide_overlay", MODE_PRIVATE)
            x = prefs.getInt("x", resources.displayMetrics.widthPixels - dp(150))
            y = prefs.getInt("y", resources.displayMetrics.heightPixels / 2)
        }

        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var moved = false
        root.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = layout.x
                    startY = layout.y
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (abs(dx) > dp(6) || abs(dy) > dp(6)) moved = true
                    layout.x = startX + dx.toInt()
                    layout.y = startY + dy.toInt()
                    try {
                        manager.updateViewLayout(root, layout)
                    } catch (_: Exception) {
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) openApp()
                    getSharedPreferences("omniaide_overlay", MODE_PRIVATE)
                        .edit()
                        .putInt("x", layout.x)
                        .putInt("y", layout.y)
                        .apply()
                    true
                }
                else -> false
            }
        }

        manager.addView(root, layout)
        overlayView = root
        params = layout
        labelView = labelViewLocal
        indicator = indicatorView
        spinner = spinnerView
        applyState()
    }

    private fun applyState() {
        val running = state == "running"
        val waiting = state == "waiting"
        val accent = when {
            waiting -> Color.parseColor("#F59E0B")
            running -> Color.parseColor("#2E7CF6")
            else -> Color.parseColor("#2E7CF6")
        }
        val background = when {
            waiting -> Color.parseColor("#F59E0B")
            running -> Color.parseColor("#2E7CF6")
            else -> Color.WHITE
        }
        val foreground = if (running || waiting) Color.WHITE else accent

        labelView?.text = label
        labelView?.setTextColor(foreground)
        indicator?.text = if (waiting) "!" else if (running) "" else "+"
        indicator?.setTextColor(foreground)
        indicator?.visibility = if (running) View.GONE else View.VISIBLE
        spinner?.visibility = if (running) View.VISIBLE else View.GONE
        spinner?.indeterminateTintList =
            android.content.res.ColorStateList.valueOf(Color.WHITE)

        val shape = GradientDrawable().apply {
            cornerRadius = dp(24).toFloat()
            setColor(background)
            if (!running && !waiting) {
                setStroke(dp(1), Color.parseColor("#D7E4F5"))
            }
        }
        overlayView?.background = shape
    }

    private fun openApp() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            if (state == "idle") putExtra(EXTRA_QUICK_CAPTURE, true)
        }
        startActivity(intent)
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}

fun startOverlayService(context: Context, label: String, state: String) {
    val intent = Intent(context, OverlayService::class.java).apply {
        action = OverlayService.ACTION_START
        putExtra(OverlayService.EXTRA_LABEL, label)
        putExtra(OverlayService.EXTRA_STATE, state)
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
    } else {
        context.startService(intent)
    }
}

fun updateOverlayService(context: Context, label: String, state: String) {
    if (!OverlayService.isRunning) return
    val intent = Intent(context, OverlayService::class.java).apply {
        action = OverlayService.ACTION_UPDATE
        putExtra(OverlayService.EXTRA_LABEL, label)
        putExtra(OverlayService.EXTRA_STATE, state)
    }
    context.startService(intent)
}

fun stopOverlayService(context: Context) {
    if (!OverlayService.isRunning) return
    val intent = Intent(context, OverlayService::class.java).apply {
        action = OverlayService.ACTION_STOP
    }
    context.startService(intent)
}
