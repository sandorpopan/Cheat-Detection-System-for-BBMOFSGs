keylogger.py

Interval-based input monitor used to distinguish a real human player
from a bot/macro during an active game session.

Behaviour:
    - Only runs while a game session is ACTIVE (not paused, not ended).
    - Every 15 seconds, wakes up and actively captures mouse + keyboard
      input for a 3 second window.
    - Outside that 3-second window it stays idle, so it has minimal
      footprint on game performance.
    - Captured samples are timestamped, encrypted (see encryption.py),
      and handed off to the pipeline for IPFS upload.

This sampling approach (short bursts rather than continuous logging)
keeps the data volume small (relevant given IPFS/blockchain storage
costs) while still being enough to fingerprint human-like input
patterns (irregular timing, natural mouse acceleration/jitter) vs.
bot-like input (perfectly uniform intervals, linear mouse paths).
"""

import time
import threading
import json
from dataclasses import dataclass, field
from typing import Callable, List

from pynput import mouse, keyboard


@dataclass
class InputSample:
    timestamp: float
    key_events: List[dict] = field(default_factory=list)
    mouse_events: List[dict] = field(default_factory=list)


class SessionKeylogger:
    CYCLE_SECONDS = 15
    CAPTURE_SECONDS = 3

    def __init__(self, on_sample_ready: Callable[[InputSample], None]):
        """
        on_sample_ready: callback invoked with a completed InputSample
                         after each 3-second capture window closes.
                         Wired up to the encryption + IPFS upload step
                         in pipeline/orchestrator.py.
        """
        self.on_sample_ready = on_sample_ready
        self._session_active = False
        self._thread = None
        self._stop_flag = threading.Event()

        self._key_listener = None
        self._mouse_listener = None
        self._current_sample = None
        self._capturing = False

    # --- session lifecycle -------------------------------------------------

    def start_session(self):
        """Call when the game session begins (e.g. match start)."""
        if self._session_active:
            return
        self._session_active = True
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_cycle_loop, daemon=True)
        self._thread.start()

    def pause_session(self):
        """Call when the game is paused. Stops capturing without
        tearing down the whole session loop."""
        self._session_active = False
        self._end_capture_window()

    def resume_session(self):
        if not self._session_active:
            self._session_active = True

    def end_session(self):
        """Call when the game session/match ends."""
        self._session_active = False
        self._stop_flag.set()
        self._end_capture_window()
        if self._thread:
            self._thread.join(timeout=1)

    # --- internal cycle ------------------------------------------------------

    def _run_cycle_loop(self):
        while not self._stop_flag.is_set():
            if self._session_active:
                self._start_capture_window()
                time.sleep(self.CAPTURE_SECONDS)
                self._end_capture_window()
                sleep_remaining = self.CYCLE_SECONDS - self.CAPTURE_SECONDS
            else:
                sleep_remaining = 1  # poll for resume/end while paused

            # sleep in small increments so pause/end is responsive
            slept = 0
            while slept < sleep_remaining and not self._stop_flag.is_set():
                time.sleep(0.5)
                slept += 0.5

    def _start_capture_window(self):
        self._current_sample = InputSample(timestamp=time.time())
        self._capturing = True

        self._key_listener = keyboard.Listener(on_press=self._on_key_press)
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move, on_click=self._on_mouse_click
        )
        self._key_listener.start()
        self._mouse_listener.start()

    def _end_capture_window(self):
        if not self._capturing:
            return
        self._capturing = False
        if self._key_listener:
            self._key_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

        if self._current_sample is not None:
            self.on_sample_ready(self._current_sample)
            self._current_sample = None

    # --- event handlers ------------------------------------------------------

    def _on_key_press(self, key):
        if self._current_sample is not None:
            self._current_sample.key_events.append(
                {"key": str(key), "t": time.time()}
            )

    def _on_mouse_move(self, x, y):
        if self._current_sample is not None:
            self._current_sample.mouse_events.append(
                {"type": "move", "x": x, "y": y, "t": time.time()}
            )

    def _on_mouse_click(self, x, y, button, pressed):
        if self._current_sample is not None:
            self._current_sample.mouse_events.append(
                {"type": "click", "x": x, "y": y, "button": str(button),
                 "pressed": pressed, "t": time.time()}
            )


def sample_to_json(sample: InputSample) -> bytes:
    return json.dumps({
        "timestamp": sample.timestamp,
        "key_events": sample.key_events,
        "mouse_events": sample.mouse_events,
    }).encode("utf-8")
