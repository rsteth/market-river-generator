resource "aws_cloudwatch_log_metric_filter" "run_failures" {
  name           = "${var.app_name}-run-failures"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.level = \"ERROR\" }"

  metric_transformation {
    name      = "RunFailures"
    namespace = var.app_name
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "slot_successes" {
  for_each = local.schedules

  name           = "${var.app_name}-${each.key}-successes"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.message = \"published latest manifest\" && $.slot = \"${each.key}\" }"

  metric_transformation {
    name      = "SlotSuccess-${each.key}"
    namespace = var.app_name
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "run_failures" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.app_name}-run-failures"
  alarm_description   = "At least one ${var.app_name} ECS run logged an error."
  namespace           = var.app_name
  metric_name         = aws_cloudwatch_log_metric_filter.run_failures.metric_transformation[0].name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "missing_slot_success" {
  for_each = var.enable_cloudwatch_alarms ? local.schedules : {}

  alarm_name          = "${var.app_name}-${each.key}-missing-success"
  alarm_description   = "No successful ${each.key} manifest publish was logged in the configured lookback window."
  namespace           = var.app_name
  metric_name         = aws_cloudwatch_log_metric_filter.slot_successes[each.key].metric_transformation[0].name
  statistic           = "Sum"
  period              = var.missing_slot_alarm_period_seconds
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}
