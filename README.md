# AWS Load Testing Demo

A deliberately basic FastAPI application for demonstrating CPU/request-rate, network, and PostgreSQL bottlenecks in an AWS class.

## Run it

The easiest option starts both the API and PostgreSQL. On the first run, PostgreSQL seeds one million rows, so startup can take a short while.

```bash
docker compose up --build
```

Open the interactive API docs at <http://localhost:8000/docs>. Stop and remove the containers with `docker compose down`. To rebuild the seed database from scratch, use `docker compose down -v` before starting again.

To run the API outside Docker, start PostgreSQL from Compose and then run:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

The default local database URL is `postgresql://demo:demo@localhost:5432/load_demo`. Override it with the `DATABASE_URL` environment variable.

## Deploy to Elastic Beanstalk

Create an Elastic Beanstalk environment using the current Python platform. The included `Procfile` starts two Uvicorn workers on `0.0.0.0:8000`, and `.ebextensions/01-healthcheck.config` configures `/healthz` as the environment health check.

Create the upload ZIP from the contents of the repository, not from its parent directory. On PowerShell:

```powershell
tar -a -c -f aws-sdm-demo-eb.zip `
  app/__init__.py app/main.py db/init.sql `
  .ebextensions/01-healthcheck.config `
  Procfile requirements.txt README.md
```

Upload `aws-sdm-demo-eb.zip` as an application version in Elastic Beanstalk and deploy it. The ZIP root must contain `Procfile`, `requirements.txt`, `.ebextensions`, and `app`; it must not contain an enclosing `aws-sdm-demo` directory.

The `/hello`, `/large-payload`, and `/healthz` endpoints work without a database. For the database endpoints:

1. Create or use a PostgreSQL database reachable from the environment instances.
2. Run `db/init.sql` against that database once.
3. Add a `DATABASE_URL` environment property under **Elastic Beanstalk > Configuration > Updates, monitoring, and logging > Environment properties**.

Use this format:

```text
postgresql://USER:PASSWORD@DATABASE_HOST:5432/DATABASE_NAME
```

Do not use `localhost` for RDS. Ensure the database security group accepts PostgreSQL traffic from the Elastic Beanstalk instance security group.

## Endpoints

### `GET /hello`

Returns a tiny response. Ramp concurrent requests against this endpoint to demonstrate request processing and EC2 CPU/load behavior.

```bash
curl http://localhost:8000/hello
# {"message":"Hello, World!"}

hey -z 30s -c 100 http://localhost:8000/hello
```

### `GET /large-payload`

Returns an exact 2 MiB JSON body. Use it to demonstrate network throughput becoming the bottleneck.

```bash
curl --output payload.json http://localhost:8000/large-payload

hey -z 30s -c 25 http://localhost:8000/large-payload
```

### `GET /db/scan/{external_id}`

Runs an intentionally bad PostgreSQL query. Applying `UPPER()` to the indexed column prevents use of the normal index and forces PostgreSQL to scan the one-million-row table. This endpoint is intentionally unsuitable for production.

```bash
curl http://localhost:8000/db/scan/8155bc545f84d9652f1012ef2bdfb6eb

hey -z 30s -c 20 http://localhost:8000/db/scan/8155bc545f84d9652f1012ef2bdfb6eb
```

Example response:

```json
{"id":1000000,"external_id":"8155bc545f84d9652f1012ef2bdfb6eb","query_ms":85.42}
```

### `GET /db/indexed/{external_id}`

Looks up the same row using the `external_id` index. Compare database CPU, query latency, and throughput with `/db/scan`.

```bash
curl http://localhost:8000/db/indexed/8155bc545f84d9652f1012ef2bdfb6eb

hey -z 30s -c 20 http://localhost:8000/db/indexed/8155bc545f84d9652f1012ef2bdfb6eb
```

## Postman

Create four GET requests with these URLs:

```text
http://localhost:8000/hello
http://localhost:8000/large-payload
http://localhost:8000/db/scan/8155bc545f84d9652f1012ef2bdfb6eb
http://localhost:8000/db/indexed/8155bc545f84d9652f1012ef2bdfb6eb
```

No headers or request bodies are required.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

## Demo notes

- Keep the Uvicorn worker count and EC2 instance size fixed when comparing endpoint behavior.
- Watch EC2 CPU/network metrics and RDS CPU, connections, and latency at the same time.
- Start with low concurrency and ramp gradually so the change in the limiting resource is visible.
- Run load tests only against infrastructure you own or are authorized to test.
