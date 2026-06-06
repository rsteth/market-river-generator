resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "app" {
  name = var.app_name

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.app_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential = true
      command   = ["python", "-m", "app.main"]
      environment = [
        {
          name  = "APP_NAME"
          value = var.app_name
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "S3_BUCKET"
          value = aws_s3_bucket.assets.bucket
        },
        {
          name  = "PUBLIC_BASE_URL"
          value = var.public_base_url
        },
        {
          name  = "IMAGE_PROVIDER"
          value = var.image_provider
        },
        {
          name  = "FAL_MODEL"
          value = var.fal_model
        },
        {
          name  = "FAL_IMAGE_SIZE"
          value = var.fal_image_size
        },
        {
          name  = "FAL_OUTPUT_FORMAT"
          value = var.fal_output_format
        },
        {
          name  = "FAL_NUM_INFERENCE_STEPS"
          value = tostring(var.fal_num_inference_steps)
        },
        {
          name  = "FAL_ACCELERATION"
          value = var.fal_acceleration
        },
        {
          name  = "FAL_ENABLE_SAFETY_CHECKER"
          value = tostring(var.fal_enable_safety_checker)
        },
        {
          name  = "REPLICATE_MODEL"
          value = var.replicate_model
        },
        {
          name  = "REPLICATE_ASPECT_RATIO"
          value = var.replicate_aspect_ratio
        },
        {
          name  = "REPLICATE_RESOLUTION"
          value = var.replicate_resolution
        },
        {
          name  = "REPLICATE_OUTPUT_FORMAT"
          value = var.replicate_output_format
        },
        {
          name  = "REPLICATE_OUTPUT_QUALITY"
          value = tostring(var.replicate_output_quality)
        },
        {
          name  = "REPLICATE_SAFETY_TOLERANCE"
          value = tostring(var.replicate_safety_tolerance)
        },
        {
          name  = "REPLICATE_SEED"
          value = var.replicate_seed == null ? "" : tostring(var.replicate_seed)
        },
        {
          name  = "PROMPT_ACTIVE_KEY"
          value = var.prompt_active_key
        },
        {
          name  = "ALLOW_BUNDLED_PROMPT_FALLBACK"
          value = tostring(var.allow_bundled_prompt_fallback)
        },
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        },
      ]
      secrets = concat(
        var.fal_key_ssm_parameter_arn == "" ? [] : [
          {
            name      = "FAL_KEY"
            valueFrom = var.fal_key_ssm_parameter_arn
          },
        ],
        var.replicate_api_token_ssm_parameter_arn == "" ? [] : [
          {
            name      = "REPLICATE_API_TOKEN"
            valueFrom = var.replicate_api_token_ssm_parameter_arn
          },
        ],
      )
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = var.app_name
        }
      }
    }
  ])

  tags = local.common_tags
}
