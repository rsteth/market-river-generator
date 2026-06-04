# market-river-generator

Small scheduled Python worker that turns simple market data into a symbolic "river city" image prompt, writes an image artifact, stores metadata in S3, and updates `manifests/latest.json` for a website to read.

## What It Does

The app runs three weekday slots:

- `open`: 6:45 AM America/Los_Angeles
- `midday`: 10:15 AM America/Los_Angeles
- `close`: 1:20 PM America/Los_Angeles

Each run fetches recent market data for `SPY`, `QQQ`, and `^VIX` using `yfinance`, derives a compact visual state, fills `prompts/river_city_v0.1.txt`, inserts weather, time-of-day, and market-condition prompt modules, generates a mock SVG by default, uploads artifacts and metadata, then updates `manifests/latest.json` last. Set `IMAGE_PROVIDER=fal` to generate real images through fal.ai.

## Data Flow

1. EventBridge Scheduler starts an ECS Fargate task.
2. The schedule passes `TASK_INPUT_JSON`, for example `{"slot":"open"}`.
3. `app.main` fetches market data and normalizes it.
4. `state.py` maps market and volatility moods to compact visual state.
5. `prompts.py` fills the prompt template with weather, time-of-day, and market-condition modules.
6. `image_model.py` uses `IMAGE_PROVIDER=mock` by default, or `IMAGE_PROVIDER=fal` for fal.ai image generation.
7. `publish.py` writes image, metadata, and finally `manifests/latest.json`.

If market data is unusable, the app writes failure metadata under `failures/` when possible and does not update `latest.json`.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For local-only runs, you may leave `S3_BUCKET` empty in `.env`. The app then writes to `runs/published/`.

Run a slot:

```bash
python -m app.main --slot open
python -m app.main --slot midday
python -m app.main --slot close
python -m app.main --slot open --weather rainy
```

Or use `TASK_INPUT_JSON`:

```bash
TASK_INPUT_JSON='{"slot":"open","weather":"cloudy"}' python -m app.main
```

## Configuration

Environment variables:

- `APP_NAME`: defaults to `market-river-generator`
- `AWS_REGION`: defaults to `us-west-2`
- `S3_BUCKET`: required for S3 publishing
- `PUBLIC_BASE_URL`: optional URL prefix, for example CloudFront
- `IMAGE_PROVIDER`: `mock`, `none`, `future`, or `fal`
- `FAL_KEY`: fal.ai API key, required when `IMAGE_PROVIDER=fal`
- `FAL_MODEL`: defaults to `fal-ai/flux/schnell`
- `FAL_IMAGE_SIZE`: defaults to `landscape_4_3`
- `FAL_OUTPUT_FORMAT`: `jpeg` or `png`, defaults to `jpeg`
- `FAL_NUM_INFERENCE_STEPS`: defaults to `4`
- `FAL_ACCELERATION`: `none`, `regular`, or `high`; defaults to `none`
- `FAL_ENABLE_SAFETY_CHECKER`: defaults to `true`
- `OUTPUT_DIR`: defaults to `runs` locally and `/tmp/market-river-generator` in Docker
- `WEATHER_CONDITION`: `sunny`, `cloudy`, or `rainy`; defaults to `sunny`
- `TASK_INPUT_JSON`: optional JSON input with `slot` and `weather`

## fal.ai Setup

Create an API key in the fal dashboard, then run locally with:

```bash
FAL_KEY="your-fal-key" IMAGE_PROVIDER=fal python -m app.main --slot open
```

For ECS, store the key in SSM Parameter Store as a SecureString, then pass its ARN to Terraform:

```bash
aws ssm put-parameter \
  --name /market-river-generator/fal-key \
  --type SecureString \
  --value "your-fal-key"
```

```hcl
image_provider            = "fal"
fal_key_ssm_parameter_arn = "arn:aws:ssm:us-west-2:123456789012:parameter/market-river-generator/fal-key"
```

If the parameter uses a customer-managed KMS key, also grant the ECS task execution role `kms:Decrypt` for that key.

## Docker

```bash
make docker-build
make docker-run-open
make docker-run-midday
make docker-run-close
```

The Docker run targets expect `.env` to exist.

## Terraform Deploy

Terraform lives in `infra/`.

```bash
make tf-init
make tf-plan
make tf-apply
```

Defaults:

- AWS region: `us-west-2`
- Bucket: `stethem-market-river-dev`
- CPU/memory: `512` / `1024`
- Log retention: 7 days
- Network: minimal public VPC and two public subnets unless `vpc_id` and `public_subnet_ids` are provided
- Public read: enabled for `images/`, `metadata/`, and `manifests/` so a website can read generated objects directly

Override values with a `terraform.tfvars` file:

```hcl
bucket_name     = "your-unique-bucket-name"
image_tag       = "latest"
public_base_url = "https://your-cloudfront-domain.example"
```

To use an existing VPC later:

```hcl
vpc_id            = "vpc-..."
public_subnet_ids = ["subnet-...", "subnet-..."]
```

## Build And Push To ECR

After `terraform apply`, get the ECR URL:

```bash
terraform -chdir=infra output -raw ecr_repository_url
```

Then:

```bash
make docker-build
make ecr-login
make docker-push ECR_REPOSITORY_URL=$(terraform -chdir=infra output -raw ecr_repository_url)
```

If you push a new tag, set `image_tag` in Terraform and apply again so the task definition points at it.

## Manual ECS Run

Export values from Terraform outputs:

```bash
export ECS_CLUSTER_NAME=$(terraform -chdir=infra output -raw ecs_cluster_name)
export ECS_TASK_DEFINITION_ARN=$(terraform -chdir=infra output -raw task_definition_arn)
export ECS_SECURITY_GROUP_ID=$(terraform -chdir=infra output -raw task_security_group_id)
export ECS_SUBNET_IDS=$(terraform -chdir=infra output -json public_subnet_ids | jq -r 'join(",")')
make run-task-open
```

The Makefile command passes `TASK_INPUT_JSON={"slot":"open"}` through ECS container overrides.

## Logs

The task logs to:

```text
/ecs/market-river-generator
```

Inspect recent logs:

```bash
aws logs describe-log-streams --log-group-name /ecs/market-river-generator --order-by LastEventTime --descending --max-items 5
aws logs tail /ecs/market-river-generator --follow
```

## S3 Layout

Successful runs:

```text
images/YYYY/MM/DD/{slot}-{run_id}.svg
metadata/YYYY/MM/DD/{slot}-{run_id}.json
manifests/latest.json
```

Failures:

```text
failures/YYYY/MM/DD/{slot}-{run_id}.json
```

`latest.json` is updated only after image and metadata writes complete. Existing manifest items for other slots are preserved; the item for the same date and slot is replaced.

## Swapping Data Or Image Providers

To replace `yfinance`, keep `fetch_market_snapshot()` returning the normalized shape used by `state.py`. That isolates future market data provider changes to `app/market.py`.

To add another real image model, implement a provider in `app/image_model.py` that returns `GeneratedImage`, then select it with `IMAGE_PROVIDER`. The current `fal` provider uses `fal-client` and defaults to `fal-ai/flux/schnell`; the `future` provider remains a deliberate TODO stub for OpenAI, Replicate, Bedrock, or another service.

## Assumptions

- The MVP uses direct S3 object URLs unless `PUBLIC_BASE_URL` is provided.
- Terraform enables public read for generated website-facing objects by default. Set `enable_public_read = false` if you will serve through CloudFront or another authenticated path.
- The worker is scheduled with EventBridge Scheduler, not an ECS Service.
- Public subnets with `assign_public_ip = true` are used to avoid NAT Gateway cost.
- The mock provider creates SVG artifacts, not real generated images.
