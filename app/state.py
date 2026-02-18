from enum import IntEnum, auto

class PlayerState(IntEnum):
    NOTHING_SPECIAL = 0
    OPENING = 1
    BUFFERING = 2
    PLAYING = 3
    PAUSED = 4
    STOPPED = 5
    ENDED = 6
    ERROR = 7

class RecorderState(IntEnum):
    IDLE = 0
    STARTING = 1
    RECORDING = 2
    STOPPING = 3
    ERROR = 4

class AppState:
    def __init__(self):
        self.player_state = PlayerState.STOPPED
        self.recorder_state = RecorderState.IDLE
        self.on_air = False
        self.is_recording = False
        self.stream_ok = True
        self.ffmpeg_available = True
