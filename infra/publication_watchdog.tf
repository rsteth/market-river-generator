# Independent, read-only task. It never runs app.main or receives provider keys.
resource "aws_iam_role" "publication_watchdog" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name               = "${var.app_name}-publication-watchdog"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "publication_watchdog" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name = "read-publication-logs"
  role = aws_iam_role.publication_watchdog[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:FilterLogEvents"]
      Resource = "${trimsuffix(aws_cloudwatch_log_group.app.arn, ":*")}:*"
    }]
  })
}

resource "aws_ecs_task_definition" "publication_watchdog" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  family                   = "${var.app_name}-publication-watchdog"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.publication_watchdog[0].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  container_definitions = jsonencode([{
    name      = "publication-watchdog"
    image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential = true
    command   = ["python", "-m", "app.publication_watchdog"]
    environment = [
      { name = "APP_NAME", value = var.app_name },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "WATCHDOG_LOG_GROUP", value = aws_cloudwatch_log_group.app.name },
      { name = "WATCHDOG_SCHEDULES", value = jsonencode({ for slot, schedule in local.schedules : slot => schedule.cron }) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "publication-watchdog"
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_iam_role" "publication_watchdog_scheduler" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name               = "${var.app_name}-watchdog-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "publication_watchdog_scheduler" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name = "run-publication-watchdog"
  role = aws_iam_role.publication_watchdog_scheduler[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = aws_ecs_task_definition.publication_watchdog[0].arn
        Condition = {
          ArnEquals = { "ecs:cluster" = aws_ecs_cluster.app.arn }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.publication_watchdog[0].arn, aws_iam_role.task_execution.arn]
        Condition = {
          StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" }
        }
      },
    ]
  })
}

resource "aws_scheduler_schedule" "publication_watchdog" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name                         = "${var.app_name}-publication-watchdog"
  description                  = "Read-only daily publication audit, including weekends."
  schedule_expression          = "cron(20 15 * * ? *)"
  schedule_expression_timezone = "America/Los_Angeles"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.app.arn
    role_arn = aws_iam_role.publication_watchdog_scheduler[0].arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.publication_watchdog[0].arn
      launch_type         = "FARGATE"
      task_count          = 1
      platform_version    = "LATEST"

      network_configuration {
        subnets          = local.subnet_ids
        security_groups  = [aws_security_group.task.id]
        assign_public_ip = true
      }
    }

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }

    input = replace(jsonencode({
      containerOverrides = [{
        name = "publication-watchdog"
        environment = [{
          name  = "WATCHDOG_SCHEDULED_AT"
          value = "__WATCHDOG_SCHEDULED_AT__"
        }]
      }]
    }), "__WATCHDOG_SCHEDULED_AT__", "<aws.scheduler.scheduled-time>")
  }

  depends_on = [
    aws_iam_role_policy.publication_watchdog,
    aws_iam_role_policy.publication_watchdog_scheduler,
    aws_cloudwatch_log_metric_filter.slot_check_failures,
    aws_cloudwatch_log_metric_filter.watchdog_heartbeat,
  ]
}
