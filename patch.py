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
    print('patched')
