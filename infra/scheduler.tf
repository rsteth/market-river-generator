resource "aws_scheduler_schedule" "market_slots" {
  for_each = local.schedules

  name                         = "${var.app_name}-${each.key}"
  description                  = "Run ${var.app_name} for the ${each.key} market slot."
  schedule_expression          = each.value.cron
  schedule_expression_timezone = "America/Los_Angeles"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.app.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.app.arn
      launch_type         = "FARGATE"
      task_count          = 1
      platform_version    = "LATEST"

      network_configuration {
        subnets          = local.subnet_ids
        security_groups  = [aws_security_group.task.id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name = local.container_name
          environment = [
            {
              name = "TASK_INPUT_JSON"
              value = jsonencode({
                slot           = each.key
                schedule_name  = "${var.app_name}-${each.key}"
                schedule_group = "default"
              })
            },
            {
              name  = "SCHEDULE_NAME"
              value = "${var.app_name}-${each.key}"
            },
            {
              name  = "SCHEDULE_SLOT"
              value = each.key
            }
          ]
        }
      ]
    })
  }
}
