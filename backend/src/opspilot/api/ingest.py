"""OTLP/HTTP (protobuf) ingest endpoints, compatible with the collector's `otlphttp` exporter."""

import gzip
import logging
import zlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from opspilot.adapters.postgres_store import PostgresStore
from opspilot.api.deps import get_store, require_ingest_token
from opspilot.config import Settings, get_settings
from opspilot.services import otlp

router = APIRouter(
    prefix="/v1/otlp/v1", tags=["ingest"], dependencies=[Depends(require_ingest_token)]
)
log = logging.getLogger(__name__)
PROTOBUF = "application/x-protobuf"


async def _body(request: Request, settings: Settings) -> bytes:
    if not request.headers.get("content-type", "").startswith(PROTOBUF):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "OTLP protobuf required")
    raw = await request.body()
    if len(raw) > settings.max_ingest_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
    if request.headers.get("content-encoding", "").lower() == "gzip":
        try:
            # Bound the decompressed size to defeat zip bombs.
            raw = zlib.decompressobj(wbits=31).decompress(raw, settings.max_ingest_bytes + 1)
        except (zlib.error, gzip.BadGzipFile, EOFError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid gzip body") from None
        if len(raw) > settings.max_ingest_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
    return raw


def _protobuf(message: object) -> Response:
    return Response(message.SerializeToString(), media_type=PROTOBUF)  # type: ignore[attr-defined]


@router.post("/traces")
async def ingest_traces(
    request: Request,
    store: Annotated[PostgresStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    body = await _body(request, settings)
    try:
        rows = otlp.decode_traces(body)
    except DecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed OTLP payload") from None
    store.insert_spans(rows)
    return _protobuf(ExportTraceServiceResponse())


@router.post("/logs")
async def ingest_logs(
    request: Request,
    store: Annotated[PostgresStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    body = await _body(request, settings)
    try:
        rows = otlp.decode_logs(body)
    except DecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed OTLP payload") from None
    store.insert_logs(rows)
    return _protobuf(ExportLogsServiceResponse())


@router.post("/metrics")
async def ingest_metrics(
    request: Request,
    store: Annotated[PostgresStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    body = await _body(request, settings)
    try:
        rows = otlp.decode_metrics(body)
    except DecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed OTLP payload") from None
    store.insert_metrics(rows)
    return _protobuf(ExportMetricsServiceResponse())
