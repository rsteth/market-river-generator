# market-river-generator

Small scheduled Python worker that turns simple market data into a symbolic "river city" image prompt, writes an image artifact, stores metadata in S3, and updates `manifests/latest.json` for a website to read.

## What It Does

The app runs three weekday slots:

- `open`: 6:45 AM America/Los_Angeles
- `midday`: 10:15 AM America/Los_Angeles
- `close`: 1:20 PM America/Los_Angeles

Each run fetches recent market data for `SPY`, `QQQ`, and `^VIX` using `yfinance`, derives a compact visual state, fills `prompts/river_city_v0.1.txt`, inserts weather, time-of-day, and market-condition prompt modules, generates a mock SVG by default, uploads artifacts and metadata, then updates `manifests/latest.json` last. Set `IMAGE_PROVIDER=fal` or `IMAGE_PROVIDER=replicate` to generate real images.

## Data Flow

1. EventBridge Scheduler starts an ECS Fargate task.
2. The schedule passes `TASK_INPUT_JSON`, for example `{"slot":"open"}`.
3. `app.main` fetches market data and normalizes it.
4. `state.py` maps market and volatility moods to compact visual state.
5. `prompts.py` fills the prompt template with weather, time-of-day, and market-condition modules.
6. `image_model.py` uses `IMAGE_PROVIDER=mock` by default, or a real provider such as `fal` or `replicate`.
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
- `AWS_REGION`: defaults to `us-east-1`
- `S3_BUCKET`: required for S3 publishing
- `PUBLIC_BASE_URL`: optional URL prefix, for example CloudFront
- `IMAGE_PROVIDER`: `mock`, `none`, `future`, `fal`, or `replicate`
- `FAL_KEY`: fal.ai API key, required when `IMAGE_PROVIDER=fal`
- `FAL_MODEL`: defaults to `fal-ai/flux/schnell`
- `FAL_IMAGE_SIZE`: defaults to `square_hd`
- `FAL_OUTPUT_FORMAT`: `jpeg` or `png`, defaults to `jpeg`
- `FAL_NUM_INFERENCE_STEPS`: defaults to `4`
- `FAL_ACCELERATION`: `none`, `regular`, or `high`; defaults to `none`
- `FAL_ENABLE_SAFETY_CHECKER`: defaults to `true`
- `REPLICATE_API_TOKEN`: Replicate API token, required when `IMAGE_PROVIDER=replicate`
- `REPLICATE_MODEL`: defaults to `black-forest-labs/flux-2-pro`
- `REPLICATE_ASPECT_RATIO`: defaults to `1:1`
- `REPLICATE_RESOLUTION`: defaults to `1 MP`
- `REPLICATE_OUTPUT_FORMAT`: defaults to `webp`
- `REPLICATE_OUTPUT_QUALITY`: defaults to `88`
- `REPLICATE_SAFETY_TOLERANCE`: defaults to `2`
- `REPLICATE_SEED`: optional integer seed for reproducible generations
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
  --value "your-fal-key" \
  --overwrite \
  --profile market-river \
  --region us-east-1
```

```hcl
image_provider            = "fal"
fal_key_ssm_parameter_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/market-river-generator/fal-key"
```

If the parameter uses a customer-managed KMS key, also grant the ECS task execution role `kms:Decrypt` for that key.

Local `.env` values are not automatically copied into ECS. Terraform passes the non-secret runtime configuration into the task definition, and `FAL_KEY` is injected only when `fal_key_ssm_parameter_arn` is set.

## Replicate Setup

Create an API token in Replicate, then run locally with:

```bash
REPLICATE_API_TOKEN="your-replicate-token" IMAGE_PROVIDER=replicate python -m app.main --slot open
```

The default Replicate model is `black-forest-labs/flux-2-pro`.

For ECS, store the token in SSM Parameter Store as a SecureString, then pass its ARN to Terraform:

```bash
aws ssm put-parameter \
  --name /market-river-generator/replicate-api-token \
  --type SecureString \
  --value "your-replicate-token" \
  --overwrite \
  --profile market-river \
  --region us-east-1
```

```hcl
image_provider                        = "replicate"
replicate_api_token_ssm_parameter_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/market-river-generator/replicate-api-token"
replicate_model                       = "black-forest-labs/flux-2-pro"
replicate_aspect_ratio                = "1:1"
replicate_resolution                  = "1 MP"
replicate_output_format               = "webp"
```

If the parameter uses a customer-managed KMS key, also grant the ECS task execution role `kms:Decrypt` for that key.

Local `.env` values are not automatically copied into ECS. Terraform passes the non-secret runtime configuration into the task definition, and `REPLICATE_API_TOKEN` is injected only when `replicate_api_token_ssm_parameter_arn` is set.

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
aws login --profile market-river --region us-east-1
make tf-init
make tf-plan
make tf-apply
```

Defaults:

- AWS region: `us-east-1`
- AWS profile: `market-river`
- Bucket: account-scoped default, or `bucket_name` if provided
- CPU/memory: `256` / `512`
- CPU architecture: `ARM64`
- Log retention: 7 days
- ECR retention: last 3 container images
- S3 generated artifact retention: 30 days for `images/`, `metadata/`, and `failures/`
- S3 manifest retention: current `manifests/latest.json` is retained; old versions expire after 30 days
- Network: minimal public VPC and two public subnets unless `vpc_id` and `public_subnet_ids` are provided
- Public read: enabled for `images/`, `metadata/`, and `manifests/` so a website can read generated objects directly

Override values with a `terraform.tfvars` file:

```hcl
bucket_name      = "your-unique-bucket-name"
image_tag        = "latest"
public_base_url  = "https://your-cloudfront-domain.example"
cpu_architecture = "ARM64"
ecr_max_image_count = 3
generated_artifact_retention_days = 30
noncurrent_version_retention_days = 30
image_provider = "replicate"
replicate_api_token_ssm_parameter_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/market-river-generator/replicate-api-token"
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

Or build, authenticate, tag, and push in one step:

```bash
make docker-release
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
images/YYYY/MM/DD/{slot}-{run_id}.{svg|jpg|png|webp}
metadata/YYYY/MM/DD/{slot}-{run_id}.json
manifests/latest.json
```

Failures:

```text
failures/YYYY/MM/DD/{slot}-{run_id}.json
```

`latest.json` is updated only after image and metadata writes complete. Existing manifest items for other slots are preserved; the item for the same date and slot is replaced.

Each manifest item includes the explicit `slot`, `created_at`, `run_id`, image and metadata URLs, market moods, the exact provider prompt, a SHA-256 `prompt.hash`, and selected model parameters. The linked metadata JSON also stores the separated positive and negative prompt fields, raw market snapshot, and derived visual state for deeper audits.

The scheduled ECS jobs run Monday through Friday only in the `America/Los_Angeles` timezone:

- `open`: 6:45 AM
- `midday`: 10:15 AM
- `close`: 1:20 PM

There is no weekend schedule. The app does not currently skip weekday market holidays unless the schedule is disabled or adjusted.

## Swapping Data Or Image Providers

To replace `yfinance`, keep `fetch_market_snapshot()` returning the normalized shape used by `state.py`. That isolates future market data provider changes to `app/market.py`.

To add another real image model, implement a provider in `app/image_model.py` that returns `GeneratedImage`, then select it with `IMAGE_PROVIDER`. The current real providers are `fal`, which uses `fal-client`, and `replicate`, which uses Replicate's Python client. Provider-specific settings stay inside the provider implementations; publishing code only receives a `GeneratedImage`.

## Assumptions

- The MVP uses direct S3 object URLs unless `PUBLIC_BASE_URL` is provided.
- Terraform enables public read for generated website-facing objects by default. Set `enable_public_read = false` if you will serve through CloudFront or another authenticated path.
- The worker is scheduled with EventBridge Scheduler, not an ECS Service.
- Public subnets with `assign_public_ip = true` are used to avoid NAT Gateway cost.
- The mock provider creates SVG artifacts, not real generated images.
