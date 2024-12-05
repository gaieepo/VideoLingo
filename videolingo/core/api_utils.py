import atexit
import functools
import inspect
import json
import os
from collections import defaultdict
from threading import Lock
from time import time


class APICounter:
    def __init__(self, save_interval=300):  # 5 minutes default
        self.COUNTER_FILE = "output/api_counter.json"
        self.lock = Lock()
        self.save_interval = save_interval
        self.last_save_time = time()
        self.counter_data = {}
        self.is_modified = False

        # Load existing data on initialization
        self._load_counter()

        # Register save on exit
        atexit.register(self.save_counter)

    def _load_counter(self):
        """Load the counter data from file"""
        if os.path.exists(self.COUNTER_FILE):
            try:
                with open(self.COUNTER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Convert regular dicts to defaultdict for module counts
                    for func in data:
                        data[func]["by_module"] = defaultdict(int, data[func]["by_module"])
                    self.counter_data = data
            except (json.JSONDecodeError, FileNotFoundError):
                self.counter_data = {}

    def save_counter(self, force=False):
        """Save the counter data to file if modified and enough time has passed"""
        if not self.is_modified:
            return

        current_time = time()
        if not force and (current_time - self.last_save_time < self.save_interval):
            return

        with self.lock:
            os.makedirs(os.path.dirname(self.COUNTER_FILE), exist_ok=True)
            # Convert defaultdict to regular dict for JSON serialization
            serializable_data = {}
            for func, data in self.counter_data.items():
                serializable_data[func] = {"total_calls": data["total_calls"], "by_module": dict(data["by_module"])}

            with open(self.COUNTER_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=4)

            self.last_save_time = current_time
            self.is_modified = False

    def increment(self, func_name, module_name):
        """Increment counters for a function call"""
        with self.lock:
            if func_name not in self.counter_data:
                self.counter_data[func_name] = {"total_calls": 0, "by_module": defaultdict(int)}

            self.counter_data[func_name]["total_calls"] += 1
            self.counter_data[func_name]["by_module"][module_name] += 1
            self.is_modified = True

            # Try to save if enough time has passed
            self.save_counter()

    def get_stats(self):
        """Get current statistics"""
        with self.lock:
            stats = {
                "total_api_calls": sum(data["total_calls"] for data in self.counter_data.values()),
                "by_function": {func: data["total_calls"] for func, data in self.counter_data.items()},
                "by_module": defaultdict(int),
            }

            for func_data in self.counter_data.values():
                for module, count in func_data["by_module"].items():
                    stats["by_module"][module] += count

            return dict(stats)


# Global counter instance
api_counter = APICounter()


def count_api_calls(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Get caller information
        frame = inspect.currentframe()
        caller_frame = frame.f_back
        while caller_frame:
            module_name = inspect.getmodule(caller_frame).__name__
            if not module_name.endswith(("ask_gpt", "ask_claude")):
                break
            caller_frame = caller_frame.f_back

        module_name = module_name if module_name else "unknown_module"

        # Increment counter
        api_counter.increment(func.__name__, module_name)

        try:
            return func(*args, **kwargs)
        finally:
            if frame:
                del frame
            if caller_frame:
                del caller_frame

    return wrapper


def print_api_stats():
    """Print a formatted summary of API usage"""
    stats = api_counter.get_stats()
    print("\nAPI Usage Statistics:")
    print("-" * 50)
    print(f"Total API calls: {stats['total_api_calls']}")

    print("\nCalls by Function:")
    for func, count in stats["by_function"].items():
        print(f"  {func}: {count}")

    print("\nCalls by Module:")
    for module, count in stats["by_module"].items():
        print(f"  {module}: {count}")


# Force save stats before program exits
def save_stats():
    api_counter.save_counter(force=True)


atexit.register(save_stats)
