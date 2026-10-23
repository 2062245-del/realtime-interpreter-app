# 소스 패치: 첫소리 잘림 방지 (Bridge.kt)
p='app/src/main/java/kr/realtime/interpreter/Bridge.kt'
s=open(p,encoding='utf-8').read()
if 'WARM' not in s:
    for a in ['onStart(utteranceId: String?) {','onError(utteranceId: String?) {','onStop(utteranceId: String?, interrupted: Boolean) {']:
        s=s.replace(a,a+' if (utteranceId == WARM) return;')
    s=s.replace('onDone(utteranceId: String?) {','onDone(utteranceId: String?) { if (utteranceId == WARM) return; lastTtsEnd = System.currentTimeMillis();')
    s=s.replace('@Volatile private var ttsSpeaking = false','@Volatile private var ttsSpeaking = false\n    @Volatile private var lastTtsEnd = 0L\n    private val WARM = "warm"')
    old='tts.speak(text, TextToSpeech.QUEUE_ADD, params, id.toString())'
    new='''val idle = !ttsSpeaking && System.currentTimeMillis() - lastTtsEnd > 2500
                ttsSpeaking = true
                try { audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_UNMUTE, 0) } catch (_: Exception) {}
                if (idle) tts.playSilentUtterance(350, TextToSpeech.QUEUE_ADD, WARM)
                '''+old
    assert s.count(old)==1
    s=s.replace(old,new)
    open(p,'w',encoding='utf-8').write(s)
    print('patched Bridge TTS')

# 2) 상시대기 고도화: 잠금화면 최신 번역 · 손님 호출 알림 · 이어폰 감지
D='app/src/main/java/kr/realtime/interpreter/'
p=D+'ListenService.kt'
if 'ACTION_UPDATE' not in open(p,encoding='utf-8').read():
    open(p,'w',encoding='utf-8').write('''package kr.realtime.interpreter

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

/**
 * 상시 대기 중 화면이 꺼지거나 다른 앱을 써도 앱이 계속 듣도록 유지하는 서비스.
 * - 알림창·잠금화면에 '최신 번역'을 계속 보여줌 (화면을 켜지 않아도 확인)
 * - 손님이 부르면 별도의 '호출 알림'(진동·팝업)을 띄움 → 누르면 바로 응대 화면
 */
class ListenService : Service() {

    companion object {
        const val CH = "listen"
        const val CH_CALL = "call"
        const val ACTION_STOP = "kr.realtime.interpreter.STOP"
        const val ACTION_UPDATE = "kr.realtime.interpreter.UPDATE"
        const val ID_MAIN = 7
        const val ID_CALL = 8
        @Volatile var running = false
    }

    private var wake: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    private fun channels(nm: NotificationManager) {
        if (Build.VERSION.SDK_INT < 26) return
        if (nm.getNotificationChannel(CH) == null) {
            nm.createNotificationChannel(NotificationChannel(CH, "통역 대기 (최신 번역)", NotificationManager.IMPORTANCE_LOW).apply {
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                setShowBadge(false)
            })
        }
        if (nm.getNotificationChannel(CH_CALL) == null) {
            nm.createNotificationChannel(NotificationChannel(CH_CALL, "손님 호출 알림", NotificationManager.IMPORTANCE_HIGH).apply {
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 120, 80, 120)
            })
        }
    }

    private fun openIntent(respond: Boolean): PendingIntent {
        val i = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (respond) i.putExtra("respond", true)
        return PendingIntent.getActivity(this, if (respond) 2 else 0, i,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun mainNotification(title: String, text: String): Notification {
        val stop = PendingIntent.getService(this, 1,
            Intent(this, ListenService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CH)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentIntent(openIntent(false))
            .addAction(0, "끄기", stop)
            .build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        channels(nm)

        if (intent?.action == ACTION_STOP) {
            MainActivity.current?.get()?.stopStandbyFromNotification()
            try { nm.cancel(ID_CALL) } catch (_: Exception) {}
            stopSelf()
            return START_NOT_STICKY
        }

        val title = intent?.getStringExtra("title") ?: "통역 대기 중"
        val text = intent?.getStringExtra("text") ?: ""

        if (intent?.action == ACTION_UPDATE && running) {
            // 최신 번역으로 알림 내용만 바꿈
            try { nm.notify(ID_MAIN, mainNotification(title, text)) } catch (_: Exception) {}
            if (intent.getBooleanExtra("call", false)) {
                val c = NotificationCompat.Builder(this, CH_CALL)
                    .setSmallIcon(R.drawable.ic_notify)
                    .setContentTitle("🙋 손님이 부르고 있어요")
                    .setContentText(text)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .setCategory(NotificationCompat.CATEGORY_MESSAGE)
                    .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                    .setAutoCancel(true)
                    .setContentIntent(openIntent(true))
                    .addAction(0, "바로 응대", openIntent(true))
                    .build()
                try { nm.notify(ID_CALL, c) } catch (_: Exception) {}
            }
            return START_STICKY
        }
        if (intent?.action == ACTION_UPDATE) { stopSelf(); return START_NOT_STICKY }

        val n = mainNotification(title, text)
        if (Build.VERSION.SDK_INT >= 29) {
            ServiceCompat.startForeground(this, ID_MAIN, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(ID_MAIN, n)
        }
        running = true

        if (wake == null) {
            val pm = getSystemService(PowerManager::class.java)
            wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "interpreter:listen").also { it.acquire(4 * 60 * 60 * 1000L) }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        try { getSystemService(NotificationManager::class.java).cancel(ID_CALL) } catch (_: Exception) {}
        try { wake?.release() } catch (_: Exception) {}
        wake = null
        super.onDestroy()
    }
}
''')
    print('patched ListenService')
p=D+'Bridge.kt';s=open(p,encoding='utf-8').read()
if 'fun bgUpdate' not in s:
    a='''    @JavascriptInterface
    fun bgStop() {'''
    assert s.count(a)==1
    s=s.replace(a,'''    /** 알림창·잠금화면에 최신 번역 표시 (call=true면 '손님 호출' 팝업 알림도) */
    @JavascriptInterface
    fun bgUpdate(title: String, text: String, call: Boolean) {
        main.post {
            if (!ListenService.running) return@post
            val i = Intent(act, ListenService::class.java).setAction(ListenService.ACTION_UPDATE)
                .putExtra("title", title).putExtra("text", text).putExtra("call", call)
            try { act.startService(i) } catch (_: Exception) {}
        }
    }

    @JavascriptInterface
    fun callClear() {
        main.post { try { (act.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).cancel(ListenService.ID_CALL) } catch (_: Exception) {} }
    }

    /** 이어폰(유선·블루투스·USB) 연결 여부 */
    @JavascriptInterface
    fun isHeadset(): Boolean {
        return try {
            audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any { d ->
                val t = d.type
                t == android.media.AudioDeviceInfo.TYPE_WIRED_HEADSET || t == android.media.AudioDeviceInfo.TYPE_WIRED_HEADPHONES ||
                t == android.media.AudioDeviceInfo.TYPE_BLUETOOTH_A2DP || t == android.media.AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                t == android.media.AudioDeviceInfo.TYPE_USB_HEADSET ||
                (Build.VERSION.SDK_INT >= 31 && t == android.media.AudioDeviceInfo.TYPE_BLE_HEADSET)
            }
        } catch (_: Exception) { false }
    }

'''+a);open(p,'w',encoding='utf-8').write(s);print('patched Bridge')
p=D+'MainActivity.kt';s=open(p,encoding='utf-8').read()
if 'onNewIntent' not in s:
    a="    /** 알림창의 '끄기' 버튼"
    assert s.count(a)==1
    s=s.replace(a,'''    /** '손님 호출' 알림을 누르면 → 웹 쪽 '바로 응대' 실행 */
    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        if (intent.getBooleanExtra("respond", false)) {
            intent.removeExtra("respond")
            bridge.js("window.__respond&&window.__respond()")
        }
    }

'''+a);open(p,'w',encoding='utf-8').write(s);print('patched MainActivity')
