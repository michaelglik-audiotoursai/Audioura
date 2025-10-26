package com.audiotours.dev

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import java.io.IOException

class NativeAudioRecorderPlugin: FlutterPlugin, MethodCallHandler {
    private lateinit var channel: MethodChannel
    private lateinit var context: Context
    private var mediaRecorder: MediaRecorder? = null
    private var isRecording = false

    override fun onAttachedToEngine(flutterPluginBinding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(flutterPluginBinding.binaryMessenger, "native_audio_recorder")
        context = flutterPluginBinding.applicationContext
        channel.setMethodCallHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: Result) {
        when (call.method) {
            "initialize" -> {
                try {
                    result.success(true)
                } catch (e: Exception) {
                    result.error("INIT_ERROR", e.message, null)
                }
            }
            "startRecording" -> {
                val filePath = call.argument<String>("filePath")
                val sampleRate = call.argument<Int>("sampleRate") ?: 44100
                val channels = call.argument<Int>("channels") ?: 1
                val bitRate = call.argument<Int>("bitRate") ?: 128000
                
                if (filePath != null) {
                    startRecording(filePath, sampleRate, channels, bitRate, result)
                } else {
                    result.error("INVALID_ARGS", "File path is required", null)
                }
            }
            "stopRecording" -> {
                stopRecording(result)
            }
            "dispose" -> {
                dispose(result)
            }
            else -> {
                result.notImplemented()
            }
        }
    }

    private fun startRecording(filePath: String, sampleRate: Int, channels: Int, bitRate: Int, result: Result) {
        try {
            if (isRecording) {
                result.error("ALREADY_RECORDING", "Already recording", null)
                return
            }

            mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(context)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }

            mediaRecorder?.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                // Force WAV format - use specific format that creates WAV files
                setOutputFormat(MediaRecorder.OutputFormat.DEFAULT)
                setAudioEncoder(MediaRecorder.AudioEncoder.DEFAULT)
                setAudioSamplingRate(sampleRate)
                setAudioChannels(channels)
                setOutputFile(filePath)

                prepare()
                start()
                isRecording = true
            }

            result.success(true)
        } catch (e: IOException) {
            result.error("RECORDING_ERROR", "Failed to start recording: ${e.message}", null)
        } catch (e: Exception) {
            result.error("UNKNOWN_ERROR", "Unknown error: ${e.message}", null)
        }
    }

    private fun stopRecording(result: Result) {
        try {
            if (!isRecording) {
                result.error("NOT_RECORDING", "Not currently recording", null)
                return
            }

            mediaRecorder?.apply {
                stop()
                release()
            }
            mediaRecorder = null
            isRecording = false

            result.success(true)
        } catch (e: Exception) {
            result.error("STOP_ERROR", "Failed to stop recording: ${e.message}", null)
        }
    }

    private fun dispose(result: Result) {
        try {
            if (isRecording) {
                mediaRecorder?.apply {
                    stop()
                    release()
                }
                isRecording = false
            }
            mediaRecorder = null
            result.success(true)
        } catch (e: Exception) {
            result.error("DISPOSE_ERROR", "Failed to dispose: ${e.message}", null)
        }
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }
}