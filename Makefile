APP_NAME ?= market-river-generator
IMAGE_TAG ?= latest
AWS_REGION ?= us-west-2
ENV_FILE ?= .env
INFRA_DIR ?= infra
ECR_REPOSITORY_URL ?=
ECS_CLUSTER_NAME ?=
ECS_TASK_DEFINITION_ARN ?=
ECS_SECURITY_GROUP_ID ?=
ECS_SUBNET_IDS ?=

.PHONY: docker-build docker-run-open docker-run-midday docker-run-close ecr-login docker-push tf-init tf-plan tf-apply run-task-open

docker-build:
	docker build -t $(APP_NAME):$(IMAGE_TAG) .

docker-run-open:
	docker run --rm --env-file $(ENV_FILE) -e TASK_INPUT_JSON='{"slot":"open"}' $(APP_NAME):$(IMAGE_TAG)

docker-run-midday:
	docker run --rm --env-file $(ENV_FILE) -e TASK_INPUT_JSON='{"slot":"midday"}' $(APP_NAME):$(IMAGE_TAG)

docker-run-close:
	docker run --rm --env-file $(ENV_FILE) -e TASK_INPUT_JSON='{"slot":"close"}' $(APP_NAME):$(IMAGE_TAG)

ecr-login:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(AWS_REGION).amazonaws.com

docker-push:
	test -n "$(ECR_REPOSITORY_URL)"
	docker tag $(APP_NAME):$(IMAGE_TAG) $(ECR_REPOSITORY_URL):$(IMAGE_TAG)
	docker push $(ECR_REPOSITORY_URL):$(IMAGE_TAG)

tf-init:
	terraform -chdir=$(INFRA_DIR) init

tf-plan:
	terraform -chdir=$(INFRA_DIR) plan

tf-apply:
	terraform -chdir=$(INFRA_DIR) apply

run-task-open:
	test -n "$(ECS_CLUSTER_NAME)"
	test -n "$(ECS_TASK_DEFINITION_ARN)"
	test -n "$(ECS_SECURITY_GROUP_ID)"
	test -n "$(ECS_SUBNET_IDS)"
	aws ecs run-task \
		--region $(AWS_REGION) \
		--cluster $(ECS_CLUSTER_NAME) \
		--launch-type FARGATE \
		--task-definition $(ECS_TASK_DEFINITION_ARN) \
		--network-configuration "awsvpcConfiguration={subnets=[$(ECS_SUBNET_IDS)],securityGroups=[$(ECS_SECURITY_GROUP_ID)],assignPublicIp=ENABLED}" \
		--overrides '{"containerOverrides":[{"name":"market-river-generator","environment":[{"name":"TASK_INPUT_JSON","value":"{\"slot\":\"open\"}"}]}]}'

