package com.audiotours.dev

import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.RecognitionListener
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.*

class MainActivity : FlutterActivity() {
    private val CHANNEL = "voice_recognition"
    private var speechRecognizer: SpeechRecognizer? = null
    private var methodChannel: MethodChannel? = null
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Register native audio recorder plugin
        flutterEngine.plugins.add(NativeAudioRecorderPlugin())
        
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
}
