from flask import Flask, request
import threading
import time
import logging
import random

from opentelemetry import trace, metrics
from opentelemetry.trace import SpanKind
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

# Tracing
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Logging
from opentelemetry._logs import set_logger_provider, get_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.trace import get_current_span

# ----- Resource -----
resource = Resource(attributes={
    SERVICE_NAME: "rranjan-flask-app_manual"
})

# ----- Traces -----
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

trace_exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(trace_exporter))

# ----- Metrics -----
metrics.set_meter_provider(
    MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint="http://otel-collector:4317", insecure=True)
            )
        ]
    )
)
meter = metrics.get_meter(__name__)
request_counter = meter.create_counter(
    name="http_requests_total",
    unit="1",
    description="Total HTTP requests"
)

# ----- Logging -----
logger_provider = LoggerProvider(resource=resource)
set_logger_provider(logger_provider)

log_exporter = OTLPLogExporter(endpoint="http://otel-collector:4317", insecure=True)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

log_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
logging.basicConfig(level=logging.INFO, handlers=[log_handler])
logger = logging.getLogger("rranjan-logger")

# ----- Flask App -----
app = Flask(__name__)

@app.route('/')
def hello():
    with tracer.start_as_current_span("hello-span", kind=SpanKind.SERVER) as span:
        # Enrich span
        span.set_attribute("endpoint", "/")
        span.set_attribute("custom.status", "success")

        # Simulate latency
        sleep_time = random.uniform(0.1, 0.3)
        time.sleep(sleep_time)
        span.set_attribute("simulated_latency_ms", int(sleep_time * 1000))

        # Increment metric
        request_counter.add(1, {"endpoint": "/"})

        # Log with trace context
        current_span = get_current_span()
        ctx = current_span.get_span_context()
        logger.info(
            "Request handled",
            extra={
                "custom_attributes": {
                    "trace_id": ctx.trace_id,
                    "span_id": ctx.span_id,
                    "endpoint": "/",
                    "latency_ms": int(sleep_time * 1000)
                }
            }
        )

        return "Hello from Flask with OTEL Traces, Metrics & Logs!"

def generate_traces_and_metrics():
    while True:
        with tracer.start_as_current_span("background_transaction", kind=SpanKind.INTERNAL) as span:
            span.set_attribute("job", "background_task")
            request_counter.add(1, {"endpoint": "/background"})

            logger.info(
                "Background transaction running",
                extra={
                    "custom_attributes": {
                        "trace_id": span.get_span_context().trace_id,
                        "span_id": span.get_span_context().span_id,
                        "task": "background_transaction"
                    }
                }
            )

            time.sleep(2)

threading.Thread(target=generate_traces_and_metrics, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
