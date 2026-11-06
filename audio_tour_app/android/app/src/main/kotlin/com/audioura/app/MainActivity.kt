package com.audioura.app

import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.RecognitionListener
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.*
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest

class MainActivity : FlutterActivity() {
    private val CHANNEL = "voice_recognition"
    private var speechRecognizer: SpeechRecognizer? = null
    private var methodChannel: MethodChannel? = null
    private var pendingResult: MethodChannel.Result? = null

    // [LOCAL-868] Share → Audioura: text/plain from another app (Musa.AI, Notes,
    // ChatGPT…) arrives as an ACTION_SEND intent. Cold start: Dart asks for it
    // (getInitialSharedText). Warm start (singleTop): onNewIntent pushes it.
    private var shareChannel: MethodChannel? = null
    private var pendingSharedText: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Register native audio recorder plugin
        flutterEngine.plugins.add(NativeAudioRecorderPlugin())
        
        shareChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.audioura.app/share")
        shareChannel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "getInitialSharedText" -> {
                    captureSharedText(intent)
                    result.success(pendingSharedText)
                    pendingSharedText = null
                }
                else -> result.notImplemented()
            }
        }

        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        methodChannel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "initialize" -> {
                    val available = SpeechRecognizer.isRecognitionAvailable(this)
                    if (available) {
                        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
                        speechRecognizer?.setRecognitionListener(createRecognitionListener())
                    }
                    result.success(available)
                }
                "startListening" -> {
                    pendingResult = result
                    startSpeechRecognition()
                }
                else -> result.notImplemented()
            }
        }

        // Attestation channel for Play Integrity (log-only → enforce)
        val attestChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.audioura.app/attestation")
        attestChannel.setMethodCallHandler { call, result ->
            when (call.method) {
                "getPlayIntegrityToken" -> {
                    val nonce = call.argument<String>("nonce") ?: ""
                    getPlayIntegrityToken(nonce, result)
                }
                else -> result.notImplemented()
            }
        }
    }

    /// Read EXTRA_TEXT from an ACTION_SEND text/plain intent, then strip it so a
    /// rotation / activity recreate does not deliver the same share twice.
    private fun captureSharedText(i: Intent?) {
        if (i == null || i.action != Intent.ACTION_SEND) return
        val type = i.type ?: return
        if (!type.startsWith("text/")) return
        val text = i.getStringExtra(Intent.EXTRA_TEXT)
        if (!text.isNullOrBlank()) pendingSharedText = text
        i.removeExtra(Intent.EXTRA_TEXT)
        i.action = Intent.ACTION_MAIN
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        captureSharedText(intent)
        val text = pendingSharedText
        if (text != null) {
            shareChannel?.invokeMethod("sharedText", text)
            pendingSharedText = null
        }
    }

    private fun startSpeechRecognition() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1000)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1000)
        }
        android.util.Log.d("VoiceRecognition", "Starting speech recognition")
        speechRecognizer?.startListening(intent)
        
        // Force stop after 3 seconds
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (pendingResult != null) {
                android.util.Log.d("VoiceRecognition", "Timeout - stopping recognition")
                speechRecognizer?.stopListening()
                pendingResult?.success("play")
                pendingResult = null
            }
        }, 3000)
    }

    private fun createRecognitionListener(): RecognitionListener {
        return object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onError(error: Int) {
                pendingResult?.success("play")
                pendingResult = null
            }
            override fun onResults(results: Bundle?) {
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                android.util.Log.d("VoiceRecognition", "All matches: $matches")
                val result = matches?.firstOrNull() ?: "play"
                android.util.Log.d("VoiceRecognition", "Selected result: $result")
                pendingResult?.success(result)
                pendingResult = null
            }
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        }
    }

    /// Calls the Play Integrity API and returns the token to Flutter.
    /// In log-only mode, this token is sent to the gateway which observes but doesn't enforce.
    private fun getPlayIntegrityToken(nonce: String, result: MethodChannel.Result) {
        try {
            val integrityManager = IntegrityManagerFactory.create(applicationContext)
            val request = IntegrityTokenRequest.builder()
                .setNonce(nonce)
                .build()
            integrityManager.requestIntegrityToken(request)
                .addOnSuccessListener { response ->
                    result.success(response.token())
                }
                .addOnFailureListener { exception ->
                    android.util.Log.e("Attestation", "Play Integrity failed: ${exception.message}")
                    result.success(null) // Return null, don't error — log-only mode
                }
        } catch (e: Exception) {
            android.util.Log.e("Attestation", "Play Integrity exception: ${e.message}")
            result.success(null) // Graceful — never block the request
        }
    }
}
