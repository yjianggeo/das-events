"""Event detection: per-channel STA/LTA with channel coincidence."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.signal import butter, sosfiltfilt
from obspy.signal.trigger import recursive_sta_lta


def bandpass_channel(x: np.ndarray, fs: float, freqmin: float, freqmax: float) -> np.ndarray:
    """Zero-phase Butterworth bandpass of one channel."""
    nyq = fs / 2.0
    hi = min(freqmax, 0.999 * nyq)
    sos = butter(4, [freqmin / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=float))


def characteristic_function(x: np.ndarray, fs: float, sta: float, lta: float) -> np.ndarray:
    """Recursive STA/LTA characteristic function of an already-filtered trace."""
    nsta = max(1, int(sta * fs))
    nlta = max(nsta + 1, int(lta * fs))
    return recursive_sta_lta(np.ascontiguousarray(x, dtype=float), nsta, nlta)
