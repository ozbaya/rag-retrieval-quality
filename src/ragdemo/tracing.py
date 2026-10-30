"""Optional Phoenix tracing. Enabled when PHOENIX_ENABLED=1 (local development only)."""
import contextlib
import json
import os

_tracer = None


def init_tracing(project: str = "rag-demo"):
    global _tracer
    if os.getenv("PHOENIX_ENABLED") != "1":
        return
    from phoenix.otel import register  # pip package: arize-phoenix-otel
    provider = register(project_name=project, auto_instrument=True)  # endpoint from PHOENIX_COLLECTOR_ENDPOINT
    _tracer = provider.get_tracer("ragdemo")


@contextlib.contextmanager
def span(name: str, **attrs):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else json.dumps(v))
        yield s
