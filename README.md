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

The `/`, `/endpoint1`, `/endpoint2`, and `/healthz` endpoints work without a database. Follow the next section to enable the database endpoints.

## Set up PostgreSQL on RDS

Create a PostgreSQL RDS instance in the same VPC as Elastic Beanstalk. For an inexpensive demo, use a Single-AZ `db.t4g.micro` with gp3 storage. The examples below assume the RDS master username is `postgres` and create an application database named `load_demo`.

### 1. Configure network access

On the RDS security group, add an inbound rule for PostgreSQL port `5432` whose source is the Elastic Beanstalk EC2 instance security group. If a separate EC2 instance will initialize the database, add its security group as another source.

```text
Type: PostgreSQL
Port: 5432
Source: sg-ELASTIC_BEANSTALK_INSTANCE_SECURITY_GROUP
```

Do not allow `0.0.0.0/0`. The database does not need to be publicly accessible when initialization runs from an EC2 instance in the VPC.

### 2. Connect from EC2

SSH to an EC2 instance that can reach RDS, clone this repository if needed, and install the PostgreSQL client. On Amazon Linux 2023:

```bash
sudo dnf install -y postgresql16
git clone https://github.com/mdanish-kh/aws-sdm-demo.git
cd aws-sdm-demo
```

Set reusable shell variables. Do not include the password in shell history:

```bash
export PGHOST="YOUR_RDS_ENDPOINT"
export PGPORT="5432"
export PGUSER="postgres"
export PGSSLMODE="require"
```

If no initial database name was provided when RDS was created, connect to PostgreSQL's default `postgres` database:

```bash
psql --dbname postgres -c "CREATE DATABASE load_demo;"
```

`psql` prompts for the RDS master password. If `load_demo` already exists, skip this command.

### 3. Create and seed the table

Run the included initialization script against `load_demo`:

```bash
psql --dbname load_demo --file db/init.sql
```

The script creates `demo_records`, inserts one million rows, creates an index on `external_id`, and analyzes the table. Verify the result:

```bash
psql --dbname load_demo --command "SELECT COUNT(*) FROM demo_records;"
# 1000000
```

The script is not idempotent. Run it once against an empty `load_demo` database.

### 4. Configure Elastic Beanstalk

Under **Elastic Beanstalk > Configuration > Updates, monitoring, and logging > Environment properties**, add:

```text
DATABASE_URL=postgresql://postgres:URL_ENCODED_PASSWORD@YOUR_RDS_ENDPOINT:5432/load_demo?sslmode=require
```

Use the RDS endpoint, not `localhost`. URL-encode special characters in the password. Applying the environment-property change restarts the application processes.

### 5. Test the database endpoints

Use the final seeded record so the intentionally bad query must scan essentially the entire table:

```bash
export API_URL="http://YOUR_ELASTIC_BEANSTALK_HOST"

curl "$API_URL/endpoint3/8155bc545f84d9652f1012ef2bdfb6eb"
curl "$API_URL/endpoint4/8155bc545f84d9652f1012ef2bdfb6eb"
```

Both requests should return ID `1000000`. Compare `query_ms`, RDS CPU, and throughput between the table-scan and indexed endpoints.

## Endpoints

### `GET /endpoint1`

Returns a tiny response. Ramp concurrent requests against this endpoint to demonstrate request processing and EC2 CPU/load behavior.

```bash
curl http://localhost:8000/endpoint1
# {"message":"Hello, World!"}

hey -z 30s -c 100 http://localhost:8000/endpoint1
```

### `GET /endpoint2`

Returns an exact 2 MiB JSON body. Use it to demonstrate network throughput becoming the bottleneck.

```bash
curl --output payload.json http://localhost:8000/endpoint2

hey -z 30s -c 25 http://localhost:8000/endpoint2
```

### `GET /endpoint3/{external_id}`

Runs an intentionally bad PostgreSQL query. Applying `UPPER()` to the indexed column prevents use of the normal index and forces PostgreSQL to scan the one-million-row table. This endpoint is intentionally unsuitable for production.

```bash
curl http://localhost:8000/endpoint3/8155bc545f84d9652f1012ef2bdfb6eb

hey -z 30s -c 20 http://localhost:8000/endpoint3/8155bc545f84d9652f1012ef2bdfb6eb
```

Example response:

```json
{"id":1000000,"external_id":"8155bc545f84d9652f1012ef2bdfb6eb","query_ms":85.42}
```

### `GET /endpoint4/{external_id}`

Looks up the same row using the `external_id` index. Compare database CPU, query latency, and throughput with `/endpoint3`.

```bash
curl http://localhost:8000/endpoint4/8155bc545f84d9652f1012ef2bdfb6eb

hey -z 30s -c 20 http://localhost:8000/endpoint4/8155bc545f84d9652f1012ef2bdfb6eb
```

## Postman

Create four GET requests with these URLs:

```text
http://localhost:8000/endpoint1
http://localhost:8000/endpoint2
http://localhost:8000/endpoint3/8155bc545f84d9652f1012ef2bdfb6eb
http://localhost:8000/endpoint4/8155bc545f84d9652f1012ef2bdfb6eb
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
