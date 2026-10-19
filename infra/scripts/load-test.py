import argparse
import http.client
import json
import os
import random
import statistics
import sys
import threading
import time
from collections import defaultdict
from urllib.parse import urlsplit

API = "/api/v1"
SCREEN = [
    "/auth/me",
    "/predictions/snapshot",
    "/predictions/summary?horizon=24&top=5",
    "/predictions?horizon=24&sort=risk_desc&limit=5000&offset=0",
    "/situations",
    "/actions",
    "/notifications?limit=100",
    "/journal?limit=2000",
    "/journal/summary",
    "/analytics/event-types",
    "/events/recent?hours=6&limit=60",
    "/system/notices",
]


class User(threading.Thread):
    def __init__(self, url: str, login: str, password: str, deadline: float, pause: float):
        super().__init__(daemon=True)
        self.target = urlsplit(url)
        self.connection = self.connect()
        self.login, self.password = login, password
        self.deadline, self.pause = deadline, pause
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, int] = defaultdict(int)
        self.screens: list[float] = []

    def connect(self) -> http.client.HTTPConnection:
        kind = (
            http.client.HTTPSConnection
            if self.target.scheme == "https"
            else http.client.HTTPConnection
        )
        return kind(self.target.netloc, timeout=30)

    def request(self, method: str, path: str, body=None, token=None) -> tuple[int, bytes]:
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token
        for _ in range(2):
            try:
                self.connection.request(
                    method, API + path, json.dumps(body) if body else None, headers
                )
                response = self.connection.getresponse()
                return response.status, response.read()
            except (OSError, http.client.HTTPException):
                self.connection.close()
                self.connection = self.connect()
        return 0, b""

    def wait(self, seconds: float) -> None:
        time.sleep(max(0.0, min(seconds, self.deadline - time.monotonic())))

    def run(self) -> None:
        credentials = {"login": self.login, "password": self.password}
        status, data = self.request("POST", "/auth/login", credentials)
        if status != 200:
            self.errors["/auth/login"] += 1
            return
        token = json.loads(data)["access_token"]
        self.wait(random.uniform(0, self.pause))
        while time.monotonic() < self.deadline:
            screen = time.perf_counter()
            for path in SCREEN:
                started = time.perf_counter()
                status, _ = self.request("GET", path, token=token)
                self.timings[path].append(time.perf_counter() - started)
                if status != 200:
                    self.errors[path] += 1
            self.screens.append(time.perf_counter() - screen)
            self.wait(random.uniform(0.5, 1.5) * self.pause)
        self.connection.close()


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="N пользователей параллельно повторяют запросы чтения интерфейса VENA"
    )
    parser.add_argument("--url", default="http://localhost:8100", help="адрес backend")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--duration", type=int, default=60, help="секунд нагрузки")
    parser.add_argument("--prefix", default="user", help="логины prefix1..prefixN")
    parser.add_argument("--pause", type=float, default=0, help="пауза между экранами, с")
    arguments = parser.parse_args()
    password = os.environ.get("VENA_LOAD_PASSWORD")
    if not password:
        parser.error("задайте пароль пользователей в VENA_LOAD_PASSWORD")

    deadline = time.monotonic() + arguments.duration
    users = [
        User(arguments.url, f"{arguments.prefix}{index}", password, deadline, arguments.pause)
        for index in range(1, arguments.users + 1)
    ]
    started = time.monotonic()
    for user in users:
        user.start()
    for user in users:
        user.join()
    elapsed = time.monotonic() - started

    timings: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    for user in users:
        for path, values in user.timings.items():
            timings[path] += values
        for path, count in user.errors.items():
            errors[path] += count
    screens = [value for user in users for value in user.screens]
    total = sum(len(values) for values in timings.values())

    print(
        f"{arguments.users} пользователей, {elapsed:.0f} с, пауза {arguments.pause:g} с, "
        f"{arguments.url}"
    )
    print("| запрос | n | p50, мс | p95, мс | max, мс | ошибки |\n|---|---|---|---|---|---|")
    for path in SCREEN:
        values = timings.get(path) or [0.0]
        print(
            f"| `{path}` | {len(timings.get(path, []))} | {statistics.median(values) * 1000:.0f} | "
            f"{percentile(values, 0.95) * 1000:.0f} | {max(values) * 1000:.0f} | {errors[path]} |"
        )
    if screens:
        print(
            f"| экран целиком ({len(SCREEN)} запросов) | {len(screens)} | "
            f"{statistics.median(screens) * 1000:.0f} | {percentile(screens, 0.95) * 1000:.0f} | "
            f"{max(screens) * 1000:.0f} | — |"
        )
    failed = sum(errors.values())
    print(f"Запросов: {total}, {total / elapsed:.1f} в секунду, ошибок: {failed}")
    if errors.get("/auth/login"):
        print(f"Не вошли: {errors['/auth/login']} пользователей", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
