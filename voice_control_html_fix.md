# Voice Control HTML Enhancement Plan

## Current Problem:
JavaScript voice commands can't find HTML elements reliably because:
- No unique IDs for audio elements
- Generic selectors like `document.querySelectorAll('audio')` fail
- No way to target specific stops

## Solution: Add Voice Control IDs to HTML Generation

### 1. Enhanced HTML Structure:
```html
<div class="tour-item" id="stop-1">
    <div class="tour-title">Stop 1: Audio 1</div>
    <audio id="audio-1" controls>
        <source src="data:audio/mpeg;base64,..." type="audio/mpeg">
    </audio>
    <button id="play-btn-1" onclick="playStop(1)">Play</button>
    <button id="pause-btn-1" onclick="pauseStop(1)">Pause</button>
</div>
```

### 2. Voice Control JavaScript Functions:
```javascript
function playStop(stopNumber) {
    const audio = document.getElementById(`audio-${stopNumber}`);
    if (audio) audio.play();
}

function pauseAllAudio() {
    document.querySelectorAll('audio').forEach(a => a.pause());
}

function nextStop() {
    // Find current playing, go to next
}

function previousStop() {
    // Find current playing, go to previous  
}
```

### 3. Mobile App JavaScript Commands:
Instead of generic selectors, use specific IDs:
- `document.getElementById('audio-1').play()`
- `playStop(2)`
- `nextStop()`
- `pauseAllAudio()`

This will make voice commands 100% reliable!