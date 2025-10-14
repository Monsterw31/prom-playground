import numpy as np
import random
from prometheus_client import Counter, Gauge, Histogram

def create_metric(name, metric_conf, label_names):
    t = metric_conf["type"]
    desc = metric_conf.get("description", name)
    if t == "counter":
        return Counter(name, desc, labelnames=label_names)
    elif t == "gauge":
        return Gauge(name, desc, labelnames=label_names)
    elif t == "histogram":
        buckets = metric_conf.get("buckets", [0.1, 0.5, 1, 2, 5])
        return Histogram(name, desc, labelnames=label_names, buckets=buckets)
    else:
        raise ValueError(f"Unsupported metric type: {t}")

def random_value(base, variance):
    return max(0, np.random.normal(base, variance))

def maybe_spike(value, conf):
    if conf["chaos"].get("enable_spikes") and random.random() < conf["chaos"]["spike_chance"]:
        return value * conf["chaos"]["spike_multiplier"]
    return value
