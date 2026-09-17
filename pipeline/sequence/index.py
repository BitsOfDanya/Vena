import numpy as np
import pandas as pd


class EventIndex:
    def __init__(self, events):
        events = events.sort_values(["channel_id", "ts"]).reset_index(drop=True)
        self.ts_sec = events["ts"].values.astype("datetime64[s]").astype(np.int64)
        state_codes, state_categories = pd.factorize(events["raw_value"].astype(str), sort=True)
        self.state_code = state_codes.astype(np.int32)
        self.state_categories = list(state_categories)
        self.vocab_size = len(self.state_categories) + 1
        self.alarm_flag = events["alarm_flag"].values.astype(np.int8)

        channel_arr = events["channel_id"].astype(str).values
        change_points = np.where(np.concatenate([[True], channel_arr[1:] != channel_arr[:-1]]))[0]
        change_points = np.append(change_points, len(channel_arr))
        self.channel_ranges = {}
        for i in range(len(change_points) - 1):
            cid = channel_arr[change_points[i]]
            self.channel_ranges[cid] = (int(change_points[i]), int(change_points[i + 1]))

    def window(self, channel_id, ts_sec, max_len):
        rng = self.channel_ranges.get(str(channel_id))
        if rng is None:
            return np.array([], dtype=np.int64), np.array([], dtype=np.int32), np.array([], dtype=np.int8), None
        start, end = rng
        ts_slice = self.ts_sec[start:end]
        pos = np.searchsorted(ts_slice, ts_sec, side="right")
        lo = max(0, pos - max_len)
        window_ts = ts_slice[lo:pos]
        window_state = self.state_code[start + lo:start + pos]
        window_alarm = self.alarm_flag[start + lo:start + pos]
        prev_ts = self.ts_sec[start + lo - 1] if lo > 0 else None
        return window_ts, window_state, window_alarm, prev_ts
