import Flutter
import UIKit
import AVFoundation

public class NativeAudioRecorderPlugin: NSObject, FlutterPlugin {
    private var audioRecorder: AVAudioRecorder?
    private var isRecording = false
    
    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(name: "native_audio_recorder", binaryMessenger: registrar.messenger())
        let instance = NativeAudioRecorderPlugin()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }
    
    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "initialize":
            initialize(result: result)
        case "startRecording":
            guard let args = call.arguments as? [String: Any],
                  let filePath = args["filePath"] as? String,
                  let sampleRate = args["sampleRate"] as? Double,
                  let channels = args["channels"] as? Int,
                  let bitRate = args["bitRate"] as? Int else {
                result(FlutterError(code: "INVALID_ARGS", message: "Invalid arguments", details: nil))
                return
            }
            startRecording(filePath: filePath, sampleRate: sampleRate, channels: channels, bitRate: bitRate, result: result)
        case "stopRecording":
            stopRecording(result: result)
        case "dispose":
            dispose(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func initialize(result: @escaping FlutterResult) {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.record, mode: .default)
            try audioSession.setActive(true)
            result(true)
        } catch {
            result(FlutterError(code: "INIT_ERROR", message: error.localizedDescription, details: nil))
        }
    }
    
    private func startRecording(filePath: String, sampleRate: Double, channels: Int, bitRate: Int, result: @escaping FlutterResult) {
        guard !isRecording else {
            result(FlutterError(code: "ALREADY_RECORDING", message: "Already recording", details: nil))
            return
        }
        
        let url = URL(fileURLWithPath: filePath)
        
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: channels,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: url, settings: settings)
            audioRecorder?.prepareToRecord()
            
            if audioRecorder?.record() == true {
                isRecording = true
                result(true)
            } else {
                result(FlutterError(code: "RECORDING_ERROR", message: "Failed to start recording", details: nil))
            }
        } catch {
            result(FlutterError(code: "RECORDING_ERROR", message: error.localizedDescription, details: nil))
        }
    }
    
    private func stopRecording(result: @escaping FlutterResult) {
        guard isRecording else {
            result(FlutterError(code: "NOT_RECORDING", message: "Not currently recording", details: nil))
            return
        }
        
        audioRecorder?.stop()
        audioRecorder = nil
        isRecording = false
        
        do {
            try AVAudioSession.sharedInstance().setActive(false)
        } catch {
            // Log error but don't fail the operation
            print("Error deactivating audio session: \(error)")
        }
        
        result(true)
    }
    
    private func dispose(result: @escaping FlutterResult) {
        if isRecording {
            audioRecorder?.stop()
            isRecording = false
        }
        audioRecorder = nil
        result(true)
    }
}