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
          name  = "LOG_LEVEL"
          value = "INFO"
        },
      ]
      secrets = var.fal_key_ssm_parameter_arn == "" ? [] : [
        {
          name      = "FAL_KEY"
          valueFrom = var.fal_key_ssm_parameter_arn
        },
      ]
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
