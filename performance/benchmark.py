"""
performance/benchmark.py
Analyzes performance test results and compares them to baseline averages.
Generates stability ratings and status labels for CPU, Disk, and Memory benchmarks.
"""

from statistics import mean

# ===============================
# Baseline Averages (reference data)
# ===============================

BASELINE = {
    "CPU": {
        "avg_iterations": 2_000_000,
        "peak_usage": 95.0,
    },
    "DISK": {
        "write_speed": 180.0,  # MB/s
        "read_speed": 200.0,   # MB/s
    },
    "MEM": {
        "write_speed": 4000.0,  # MB/s
        "read_speed": 6000.0,   # MB/s
        "errors": 0,
    }
}


# ===============================
# Utility Functions
# ===============================

def compare_value(value: float, baseline: float, tolerance: float = 0.15) -> str:
    """
    Compares a metric to baseline value and returns:
      'Excellent', 'Stable', 'Below Average', or 'Critical'
    """
    if baseline == 0:
        return "Unknown"
    ratio = value / baseline
    if ratio >= 1.2:
        return "Excellent"
    elif 1.0 - tolerance <= ratio <= 1.2:
        return "Stable"
    elif 0.7 <= ratio < (1.0 - tolerance):
        return "Below Average"
    else:
        return "Critical"


def score_performance(results: dict, category: str) -> dict:
    """
    Takes test results and assigns performance rating per category.
    Input `results` must match the test type:
      - CPU: {'iterations', 'avg_cpu_usage', 'peak_cpu_usage'}
      - DISK: {'write_speed', 'read_speed'}
      - MEM: {'write_speed', 'read_speed', 'errors'}
    Returns a dict with ratings and average score.
    """
    ratings = {}
    total_score = []

    try:
        if category == "CPU":
            ratings["Iterations"] = compare_value(results.get("iterations", 0), BASELINE["CPU"]["avg_iterations"])
            ratings["Peak Usage"] = compare_value(results.get("peak_cpu_usage", 0), BASELINE["CPU"]["peak_usage"])
            total_score.extend([_score_level(ratings["Iterations"]), _score_level(ratings["Peak Usage"])])

        elif category == "DISK":
            ratings["Write Speed"] = compare_value(results.get("write_speed", 0), BASELINE["DISK"]["write_speed"])
            ratings["Read Speed"] = compare_value(results.get("read_speed", 0), BASELINE["DISK"]["read_speed"])
            total_score.extend([_score_level(ratings["Write Speed"]), _score_level(ratings["Read Speed"])])

        elif category == "MEM":
            ratings["Write Speed"] = compare_value(results.get("write_speed", 0), BASELINE["MEM"]["write_speed"])
            ratings["Read Speed"] = compare_value(results.get("read_speed", 0), BASELINE["MEM"]["read_speed"])
            errors = results.get("errors", 0)
            ratings["Integrity"] = "Stable" if errors == 0 else "Critical"
            total_score.extend([
                _score_level(ratings["Write Speed"]),
                _score_level(ratings["Read Speed"]),
                5 if errors == 0 else 1
            ])
        else:
            ratings["Status"] = "Unknown"

        ratings["Overall Score"] = round(mean(total_score), 1) if total_score else 0
        ratings["Overall Rating"] = _rating_from_score(ratings["Overall Score"])
        return ratings

    except Exception:
        return {"Status": "Error", "Overall Score": 0, "Overall Rating": "Unknown"}


def _score_level(label: str) -> int:
    """
    Converts rating label to numeric value for averaging.
    """
    return {"Excellent": 10, "Stable": 8, "Below Average": 5, "Critical": 2}.get(label, 0)


def _rating_from_score(score: float) -> str:
    """
    Converts numeric score to human-readable performance level.
    """
    if score >= 9:
        return "Excellent"
    elif score >= 7:
        return "Stable"
    elif score >= 5:
        return "Below Average"
    else:
        return "Critical"


# ===============================
# Example Composite Function
# ===============================

def summarize_benchmark(cpu_result=None, disk_result=None, mem_result=None) -> dict:
    """
    Produces a unified system benchmark summary.
    Returns {'CPU': {...}, 'DISK': {...}, 'MEM': {...}, 'Overall': str}
    """
    summary = {}
    scores = []

    if cpu_result:
        cpu_score = score_performance(cpu_result, "CPU")
        summary["CPU"] = cpu_score
        scores.append(cpu_score["Overall Score"])
    if disk_result:
        disk_score = score_performance(disk_result, "DISK")
        summary["DISK"] = disk_score
        scores.append(disk_score["Overall Score"])
    if mem_result:
        mem_score = score_performance(mem_result, "MEM")
        summary["MEM"] = mem_score
        scores.append(mem_score["Overall Score"])

    if scores:
        avg_score = round(mean(scores), 1)
        summary["Overall"] = _rating_from_score(avg_score)
    else:
        summary["Overall"] = "Unknown"

    return summary
