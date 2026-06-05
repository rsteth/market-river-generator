data "aws_caller_identity" "current" {}

locals {
  common_tags = {
    App = var.app_name
  }

  container_name = var.app_name
  bucket_name    = var.bucket_name != "" ? var.bucket_name : "${var.app_name}-${data.aws_caller_identity.current.account_id}-dev"

  schedules = {
    open = {
      cron = "cron(45 6 ? * MON-FRI *)"
    }
    midday = {
      cron = "cron(15 10 ? * MON-FRI *)"
    }
    close = {
      cron = "cron(20 13 ? * MON-FRI *)"
    }
  }
}
