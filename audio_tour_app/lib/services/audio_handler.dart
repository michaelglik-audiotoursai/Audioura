import 'package:audio_service/audio_service.dart';
import 'package:just_audio/just_audio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';

class AudioPlayerHandler extends BaseAudioHandler with QueueHandler, SeekHandler {
  final AudioPlayer _player = AudioPlayer();
  
  AudioPlayerHandler() {
    print('=== AudioPlayerHandler Constructor ===');
    print('Creating MediaBrowserService handler for Android Auto');
    
    // Initialize with basic stopped state that Android Auto can recognize
    playbackState.add(PlaybackState(
      controls: [MediaControl.play, MediaControl.pause, MediaControl.stop],
      systemActions: const {
        MediaAction.seek,
        MediaAction.seekForward,
        MediaAction.seekBackward,
      },
      androidCompactActionIndices: const [0, 1, 2],
      processingState: AudioProcessingState.ready,
      playing: false,
      updatePosition: Duration.zero,
      bufferedPosition: Duration.zero,
      speed: 1.0,
    ));
    
    _initializeQueue();
    print('AudioPlayerHandler: Ready for Android Auto queries');
  }

  void _initializeQueue() {
    // Queue will be populated dynamically from saved tours
  }

  @override
  Future<List<MediaItem>> getChildren(String parentMediaId, [Map<String, dynamic>? options]) async {
    print('=== getChildren called ===');
    print('parentMediaId: $parentMediaId');
    print('AudioService.browsableRootId: ${AudioService.browsableRootId}');
    print('options: $options');
    
    try {
      if (parentMediaId == AudioService.browsableRootId) {
        print('Returning root items for Android Auto');
        final rootItems = [
          MediaItem(
            id: 'tours',
            title: 'My Audio Tours',
            playable: false,
          ),
        ];
        print('Root items: ${rootItems.map((e) => e.title).toList()}');
        return rootItems;
      }
      
      if (parentMediaId == 'tours') {
        final tours = await _loadSavedTours();
        print('Returning ${tours.length} tours');
        return tours;
      }
      
      print('No matching parentMediaId, returning empty list');
      return [];
    } catch (e) {
      print('Error in getChildren: $e');
      return [];
    }
  }

  Future<List<MediaItem>> _loadSavedTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final toursJson = prefs.getStringList('saved_tours') ?? [];
      
      return toursJson.map((tourJson) {
        final tour = json.decode(tourJson);
        return MediaItem(
          id: tour['audioUrl'] ?? '',
          title: tour['title'] ?? 'Untitled Tour',
          artist: 'AudioTours',
          duration: Duration(seconds: tour['duration'] ?? 300),
        );
      }).toList();
    } catch (e) {
      return [
        MediaItem(
          id: 'no_tours',
          title: 'No tours available',
          artist: 'AudioTours',
          playable: false,
        ),
      ];
    }
  }

  @override
  Future<void> play() => _player.play();

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> playMediaItem(MediaItem mediaItem) async {
    this.mediaItem.add(mediaItem);
    await _player.setUrl(mediaItem.id);
    await _player.play();
  }

  @override
  Future<void> seek(Duration position) => _player.seek(position);

  PlaybackState _transformEvent(PlaybackEvent event) {
    return PlaybackState(
      controls: [
        MediaControl.rewind,
        if (_player.playing) MediaControl.pause else MediaControl.play,
        MediaControl.fastForward,
      ],
      systemActions: const {
        MediaAction.seek,
        MediaAction.seekForward,
        MediaAction.seekBackward,
      },
      androidCompactActionIndices: const [0, 1, 2],
      processingState: const {
        ProcessingState.idle: AudioProcessingState.idle,
        ProcessingState.loading: AudioProcessingState.loading,
        ProcessingState.buffering: AudioProcessingState.buffering,
        ProcessingState.ready: AudioProcessingState.ready,
        ProcessingState.completed: AudioProcessingState.completed,
      }[_player.processingState]!,
      playing: _player.playing,
      updatePosition: _player.position,
      bufferedPosition: _player.bufferedPosition,
      speed: _player.speed,
      queueIndex: event.currentIndex,
    );
  }
}