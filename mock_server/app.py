from flask import Flask, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram
import threading
import time
import yaml
from pathlib import Path
import os
import itertools
import random
from utils.metric_gen import create_metric, random_value, maybe_spike
from typing import cast
from utils.pattern_generator import PatternMetricGenerator
import logging
from pathlib import Path

app = Flask(__name__)

# Load config
config_path = Path(__file__).parent / "config.yml"
with open(config_path) as f:
    config = yaml.safe_load(f)

# Load pattern-config
pattern_config_path = Path(__file__).parent / "pattern_config.yml"
with open(pattern_config_path) as f:
    pattern_config = yaml.safe_load(f)

metrics_conf = config["metrics"]
labels_conf = config["labels"]
label_names = list(labels_conf.keys())
chaos = config.get("chaos", {})
update_interval = config.get("update_interval_seconds", 2)
num_labels = config.get("num_label_combinations", 10)

# Generate label combos
label_combinations = [
    dict(zip(label_names, combo))
    for combo in itertools.product(*(labels_conf[l] for l in label_names))
]

metrics: dict[str, Counter | Gauge | Histogram] = {
    name: create_metric(name, conf, label_names)
    for name, conf in metrics_conf.items()
}

trend_tracker = {name: conf.get("base_value", 1) for name, conf in metrics_conf.items()}

def apply_latency_trend(name, base_value, conf):
    if not chaos.get("enable_latency_trend"): return base_value
    drift = chaos.get("latency_drift_per_tick", 0.1)
    direction = conf.get("drift_direction", "up")
    if direction == "up":
        trend_tracker[name] += drift
    else:
        trend_tracker[name] -= drift
    return max(0, trend_tracker[name])

def maybe_skip_metric():
    return chaos.get("enable_missing_metrics") and random.random() < chaos.get("missing_metric_chance", 0)

def maybe_skip_labelset():
    return chaos.get("enable_dropouts") and random.random() < chaos.get("dropout_chance", 0)

def maybe_flip_status(labels):
    # avoid mutating the shared label_combinations entries
    labels = labels.copy()
    if chaos.get("enable_status_flips") and random.random() < chaos.get("status_flip_chance", 0):
        labels["status"] = random.choice(["200", "500"])
    return labels

def update_metrics():
    while True:
        for name, metric in metrics.items():
            if maybe_skip_metric():
                continue

            conf = metrics_conf[name]
            base = conf.get("base_value", 1)
            var = conf.get("variance", 0.2)
            base = apply_latency_trend(name, base, conf)
            val = maybe_spike(random_value(base, var), config)

            for labels in random.sample(label_combinations, min(num_labels, len(label_combinations))):
                if maybe_skip_labelset():
                    continue
                labels = maybe_flip_status(labels)

                metric_type = conf["type"]
                # Use typing.cast so the static checker knows which Prometheus metric type
                if metric_type == "counter":
                    cast(Counter, metric).labels(**labels).inc(val)
                elif metric_type == "gauge":
                    cast(Gauge, metric).labels(**labels).set(val)
                elif metric_type == "histogram":
                    cast(Histogram, metric).labels(**labels).observe(val)

            # sleep once per update cycle (after processing all label sets for this metric)
            time.sleep(update_interval)

# Setup simple file loggers for chaos (main update loop) and pattern generator
# Prefer an environment-provided LOG_DIR (useful when running inside container);
# otherwise fall back to repository-root ./logs
repo_root = Path(__file__).resolve().parents[1]
default_logs_dir = repo_root / "logs"
log_dir_env = os.environ.get("LOG_DIR")
if log_dir_env:
    logs_dir = Path(log_dir_env)
else:
    logs_dir = default_logs_dir
logs_dir.mkdir(parents=True, exist_ok=True)

# Ensure log files exist (create empty files) so handlers can open them reliably
for _fname in ("chaos.log", "pattern.log"):
    p = logs_dir / _fname
    try:
        # create empty file if missing
        with p.open("a", encoding="utf-8") as _f:
            pass
    except Exception as _ex:
        # If we cannot create files (mount/permissions), warn but continue
        logging.getLogger(__name__).warning(f"Unable to create log file {p}: {_ex}")

chaos_logger = logging.getLogger("chaos_logger")
chaos_logger.setLevel(logging.INFO)
chaos_fh = logging.FileHandler(logs_dir / "chaos.log", encoding="utf-8")
chaos_fh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
chaos_logger.addHandler(chaos_fh)

pattern_logger = logging.getLogger("pattern_logger")
pattern_logger.setLevel(logging.INFO)
pattern_fh = logging.FileHandler(logs_dir / "pattern.log", encoding="utf-8")
pattern_fh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
pattern_logger.addHandler(pattern_fh)

# Create the pattern generator and inject shared metrics and its logger
pattern_generator = PatternMetricGenerator(pattern_config, metrics=metrics, logger=pattern_logger)

@app.route("/metrics")
def metrics_endpoint():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route("/")
def index():
    return "Mock Prometheus metrics server (configurable chaos edition) is running!"

@app.route('/pattern/reset')
def reset_pattern():
    """Endpoint to reset pattern generator timer"""
    pattern_generator.reset_timer()
    return "Pattern timer reset"

@app.route('/pattern/status')
def pattern_status():
    """Endpoint to check current pattern phase"""
    phase = pattern_generator.get_current_phase()
    return {"current_phase": phase}

if __name__ == "__main__":
    chaos_thread = threading.Thread(target=update_metrics, daemon=True)
    chaos_thread.start()
    pattern_generator.start()
    app.run(host="0.0.0.0", port=9100)
