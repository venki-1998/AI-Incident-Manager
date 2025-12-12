from prometheus_client import start_http_server, Counter

# Metrics
INCIDENTS_PROCESSED = Counter('incident_processed_total', 'Number of incidents processed')

def start_metrics_server(port: int = 8000):
    start_http_server(port)
    print(f"📊 Prometheus metrics server started on port {port}")