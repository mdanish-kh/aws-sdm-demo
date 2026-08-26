import asyncio
import os
from contextlib import asynccontextmanager
from time import perf_counter

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://demo:demo@localhost:5432/load_demo",
)
PAYLOAD_SIZE = 2 * 1024 * 1024
LARGE_JSON = b'{"data":"' + (b"x" * (PAYLOAD_SIZE - 11)) + b'"}'


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = None
    app.state.db_pool_lock = asyncio.Lock()
    yield
    if app.state.db_pool is not None:
        await app.state.db_pool.close()


app = FastAPI(
    title="AWS Load Testing Demo",
    description="Intentionally simple endpoints for demonstrating different bottlenecks.",
    lifespan=lifespan,
)


async def get_pool(request: Request) -> asyncpg.Pool:
    if request.app.state.db_pool is None:
        async with request.app.state.db_pool_lock:
            if request.app.state.db_pool is None:
                request.app.state.db_pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    command_timeout=60,
                )
    return request.app.state.db_pool


async def run_lookup(request: Request, query: str, external_id: str) -> dict:
    started_at = perf_counter()
    try:
        pool = await get_pool(request)
        async with pool.acquire() as connection:
            row = await connection.fetchrow(query, external_id)
    except (asyncpg.PostgresError, OSError) as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")

    return {
        "id": row["id"],
        "external_id": row["external_id"],
        "query_ms": round((perf_counter() - started_at) * 1000, 2),
    }


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello", summary="Small response for CPU/request-rate testing")
async def hello() -> dict[str, str]:
    return {"message": "Hello, World!"}


@app.get("/large-payload", summary="Return an exact 2 MiB JSON response")
async def large_payload() -> Response:
    return Response(content=LARGE_JSON, media_type="application/json")


@app.get("/db/scan/{external_id}", summary="Intentionally slow table scan")
async def table_scan(request: Request, external_id: str) -> dict:
    # UPPER(column) prevents the normal external_id index from being used.
    return await run_lookup(
        request,
        "SELECT id, external_id FROM demo_records WHERE UPPER(external_id) = UPPER($1)",
        external_id,
    )


@app.get("/db/indexed/{external_id}", summary="Fast indexed lookup")
async def indexed_lookup(request: Request, external_id: str) -> dict:
    return await run_lookup(
        request,
        "SELECT id, external_id FROM demo_records WHERE external_id = $1",
        external_id,
    )


@app.get("/healthz", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
