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

resource "aws_cloudwatch_log_metric_filter" "slot_calendar_skips" {
  for_each = local.schedules

  name           = "${var.app_name}-${each.key}-calendar-skips"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.message = \"market slot skipped by calendar\" && $.slot = \"${each.key}\" }"

  metric_transformation {
    name      = "SlotCalendarSkip-${each.key}"
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
  alarm_description   = "Daily calendar-aware check found a missed execution, missing publication or invalid skip for ${each.key}. See publication watchdog result logs."
  namespace           = var.app_name
  metric_name         = aws_cloudwatch_log_metric_filter.slot_check_failures[each.key].metric_transformation[0].name
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

# Every completed check emits 0 (healthy) or 1 (requires attention).
# A separate heartbeat covers a watchdog that never starts or finishes.
resource "aws_cloudwatch_log_metric_filter" "slot_check_failures" {
  for_each = var.enable_cloudwatch_alarms ? local.schedules : {}

  name           = "${var.app_name}-${each.key}-check-failures"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.message = \"publication watchdog result\" && $.slot = \"${each.key}\" && $.alarm = * }"

  metric_transformation {
    name      = "SlotCheckFailure-${each.key}"
    namespace = var.app_name
    value     = "$.alarm"
  }
}

resource "aws_cloudwatch_log_metric_filter" "watchdog_heartbeat" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name           = "${var.app_name}-publication-watchdog-heartbeat"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.message = \"publication watchdog completed\" }"

  metric_transformation {
    name      = "PublicationWatchdogHeartbeat"
    namespace = var.app_name
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "watchdog_missing" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.app_name}-publication-watchdog-missing"
  alarm_description   = "No completed daily publication check; includes weekends. Allow 26 hours for DST and delivery delay."
  namespace           = var.app_name
  metric_name         = aws_cloudwatch_log_metric_filter.watchdog_heartbeat[0].metric_transformation[0].name
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 26
  datapoints_to_alarm = 26
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}
