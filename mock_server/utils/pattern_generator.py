import threading
import time
import datetime
from prometheus_client import Gauge, Histogram, Counter
from typing import Dict, Any, cast, Optional
import logging

class PatternMetricGenerator:
    def __init__(self, config: Dict[str, Any], metrics: Optional[Dict[str, Any]], logger: Optional[logging.Logger]):
        self.config = config
        self.pattern_config = config.get("pattern_generator", {})
        self.enabled = self.pattern_config.get("enabled", False)
        self.start_time = None
        self.thread = None
        self.running = False
        
        # Metrics can be injected from the main application to ensure we reuse the
        # same Prometheus metric objects (avoids duplicates). If not provided,
        # the generator will create local metrics (backwards compatible).
        self.pattern_metrics: Dict[str, Counter | Gauge | Histogram] = metrics or {}
        # optional logger for writing pattern events to a file
        self.logger: Optional[logging.Logger] = logger

    def get_current_phase(self) -> Dict[str, Any]:
        """Get current phase based on elapsed time"""
        if not self.start_time:
            self.start_time = datetime.datetime.now()

        elapsed_seconds = (datetime.datetime.now() - self.start_time).total_seconds()

        phases = self.pattern_config.get("phases", [])
        for phase in phases:
            start = phase.get("start_seconds", 0)
            duration = phase.get("duration_seconds", 0)
            if start <= elapsed_seconds < start + duration:
                return phase

        # If no phase matches, return default
        return {"name": "completed", "generate": False}

    def _generate_pattern_metrics(self):
        """Generate metrics based on current pattern phase"""
        while self.running:
            if not self.enabled:
                time.sleep(1)
                continue
            
            phase = self.get_current_phase()
            
            # Skip if phase says not to generate
            if not phase.get("generate", True):
                time.sleep(0.5)  # Check more frequently during off phases
                continue
            
            # Generate metrics for this phase
            labels = {
                "app": "mock_pattern",
                "status": phase.get("status", "200"),
                "method": "GET",
                "uri": "/api/data", 
                "env": "prod"
            }

            # Set histogram observation (cast to Histogram to satisfy static checkers)
            latency = phase.get("latency", 0.1)
            hist = self.pattern_metrics.get("http_server_requests_seconds")
            if hist is not None:
                cast(Histogram, hist).labels(**labels).observe(latency)

            # Set max gauge
            max_latency = phase.get("max_latency", latency * 1.5)
            g = self.pattern_metrics.get("http_server_requests_seconds_max")
            if g is not None:
                cast(Gauge, g).labels(**labels).set(max_latency)

            print(f"Pattern Generator - Phase: {phase.get('name', 'unknown')}, Status: {labels['status']}")
            msg = f"Phase={phase.get('name', 'unknown')} status={labels['status']} latency={latency} max_latency={max_latency} uri={labels.get('uri')}"
            if self.logger:
                self.logger.info(msg)
            else:
                print(f"ePattern Generator - {msg}")

            # Sleep based on phase frequency
            sleep_time = phase.get("interval_seconds", 1.0)
            time.sleep(sleep_time)

    def start(self):
        """Start the pattern generator in a separate thread"""
        if not self.enabled:
            print("Pattern generator is disabled")
            return
        
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._generate_pattern_metrics, daemon=True)
        self.thread.start()
        print("Pattern generator started")
    
    def stop(self):
        """Stop the pattern generator"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        print("Pattern generator stopped")
    
    def reset_timer(self):
        """Reset the pattern timer to start from beginning"""
        self.start_time = datetime.datetime.now()
        print("Pattern generator timer reset")
