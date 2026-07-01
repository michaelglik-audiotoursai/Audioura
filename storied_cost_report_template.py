"""
storied_cost_report_template.py — Weekly cost monitoring script.
=================================================================
Task [S73]. Reads service stdout logs from docker logs, counts tour metrics.
Prints a weekly summary table.

Usage:
    python storied_cost_report_template.py [--days 7]
"""
import os
import sys
import re
import subprocess
import argparse
from datetime import datetime, timedelta


def get_docker_logs(container_name, since_hours=168):
    """Get docker logs for the specified container from the last N hours."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--since", f"{since_hours}h", container_name],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        print("WARNING: docker command not found — using empty logs")
        return ""
    except subprocess.TimeoutExpired:
        print("WARNING: docker logs timed out")
        return ""
    except Exception as e:
        print(f"WARNING: Could not get docker logs: {e}")
        return ""


def parse_metrics(log_text):
    """Extract tour generation metrics from log text."""
    metrics = {
        "total_tours": 0,
        "storied_tours": 0,
        "total_cost": 0.0,
        "ceiling_exceeded": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }

    # Count total tours (any generation start)
    metrics["total_tours"] = len(re.findall(r"GENERATE_TOUR_TEXT_FUNCTION_ENTRY|GENERATOR_SERVICE_ASYNC_START", log_text))

    # Count Storied tours
    metrics["storied_tours"] = len(re.findall(r"\[Storied\] STORIED_MODE=true", log_text))

    # Sum costs (from "Total API cost: $X.XXXX" lines)
    cost_matches = re.findall(r"Total API cost: \$([0-9.]+)", log_text)
    metrics["total_cost"] = sum(float(c) for c in cost_matches)

    # Count ceiling exceeded events
    metrics["ceiling_exceeded"] = len(re.findall(r"COST CEILING EXCEEDED", log_text))

    # Count cache hits/misses
    metrics["cache_hits"] = len(re.findall(r"CACHE HIT:", log_text))
    metrics["cache_misses"] = len(re.findall(r"CACHE MISS:", log_text))

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Storied weekly cost report")
    parser.add_argument("--days", type=int, default=7, help="Number of days to report on")
    parser.add_argument("--container", type=str, default="development-tour-generator-1",
                       help="Docker container name")
    args = parser.parse_args()

    hours = args.days * 24
    container = args.container

    print("=" * 60)
    print(f"Storied Cost Report — Last {args.days} day(s)")
    print(f"Container: {container}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Get logs
    log_text = get_docker_logs(container, hours)

    if not log_text.strip():
        print("\nNo tour logs found for period.")
        print("(Container may not be running or no tours were generated)")
        sys.exit(0)

    # Parse metrics
    metrics = parse_metrics(log_text)

    # Print report table
    print(f"\n{'Metric':<30} {'Value':>15}")
    print("-" * 47)
    print(f"{'Total tours generated':<30} {metrics['total_tours']:>15}")
    print(f"{'Storied mode tours':<30} {metrics['storied_tours']:>15}")
    _cost_str = f"${metrics['total_cost']:.4f}"
    print(f"{'Total API cost':<30} {_cost_str:>15}")
    print(f"{'Cost ceiling exceeded':<30} {metrics['ceiling_exceeded']:>15}")
    print(f"{'Cache hits':<30} {metrics['cache_hits']:>15}")
    print(f"{'Cache misses':<30} {metrics['cache_misses']:>15}")

    # Derived metrics
    if metrics["total_tours"] > 0:
        avg_cost = metrics["total_cost"] / metrics["total_tours"]
        _avg_str = f"${avg_cost:.4f}"
        print(f"\n{'Avg cost per tour':<30} {_avg_str:>15}")
    if metrics["cache_hits"] + metrics["cache_misses"] > 0:
        hit_rate = metrics["cache_hits"] / (metrics["cache_hits"] + metrics["cache_misses"]) * 100
        print(f"{'Cache hit rate':<30} {f'{hit_rate:.1f}%':>15}")

    print("\n" + "=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
