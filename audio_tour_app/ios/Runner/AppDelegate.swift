import Flutter
import UIKit
import Speech
import AVFoundation
import workmanager_apple

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var speechRecognizer: SFSpeechRecognizer?
  private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
  private var recognitionTask: SFSpeechRecognitionTask?
  private let audioEngine = AVAudioEngine()
  
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)

    // [LOCAL-714 / D675 part 2] Register the community-tours BGTaskScheduler
    // identifier so iOS can run the background CHECK with the app closed. The
    // identifier MUST also be listed under BGTaskSchedulerPermittedIdentifiers
    // in Info.plist (it is: com.audioura.community_tours_sync). On iOS this is a
    // BGAppRefreshTask (app refresh) — the Dart entry point (callbackDispatcher)
    // runs the CHECK-only notification path there (no background download).
    WorkmanagerPlugin.setPluginRegistrantCallback { registry in
      GeneratedPluginRegistrant.register(with: registry)
    }
    if #available(iOS 13.0, *) {
      WorkmanagerPlugin.registerPeriodicTask(
        withIdentifier: "com.audioura.community_tours_sync")
      WorkmanagerPlugin.registerLaunchHandlers()
    }
    
    // Register native audio recorder plugin
    let controller = window?.rootViewController as! FlutterViewController
    NativeAudioRecorderPlugin.register(with: self.registrar(forPlugin: "NativeAudioRecorderPlugin")!)
    
    let channel = FlutterMethodChannel(name: "voice_recognition", binaryMessenger: controller.binaryMessenger)
    
    channel.setMethodCallHandler { [weak self] (call, result) in
      switch call.method {
      case "initialize":
        self?.initializeSpeech(result: result)
      case "startListening":
        self?.startListening(result: result)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
    
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
  
  private func initializeSpeech(result: @escaping FlutterResult) {
    speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    
    SFSpeechRecognizer.requestAuthorization { authStatus in
      DispatchQueue.main.async {
        result(authStatus == .authorized)
      }
    }
  }
  
  private func startListening(result: @escaping FlutterResult) {
    guard let speechRecognizer = speechRecognizer, speechRecognizer.isAvailable else {
      result("play")
      return
    }
    
    recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
    guard let recognitionRequest = recognitionRequest else {
      result("play")
      return
    }
    
    recognitionRequest.shouldReportPartialResults = false
    
    recognitionTask = speechRecognizer.recognitionTask(with: recognitionRequest) { recognitionResult, error in
      if let recognitionResult = recognitionResult {
        if recognitionResult.isFinal {
          result(recognitionResult.bestTranscription.formattedString)
          self.stopListening()
        }
      } else {
        result("play")
        self.stopListening()
      }
    }
    
    let inputNode = audioEngine.inputNode
    let recordingFormat = inputNode.outputFormat(forBus: 0)
    
    inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
      recognitionRequest.append(buffer)
    }
    
    audioEngine.prepare()
    try? audioEngine.start()
    
    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
      self.stopListening()
    }
  }
  
  private func stopListening() {
    audioEngine.stop()
    audioEngine.inputNode.removeTap(onBus: 0)
    recognitionRequest?.endAudio()
    recognitionTask?.cancel()
  }
}
