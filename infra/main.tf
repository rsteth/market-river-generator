data "aws_caller_identity" "current" {}

locals {
  common_tags = {
    App = var.app_name
  }

  container_name = var.app_name
  bucket_name    = var.bucket_name != "" ? var.bucket_name : "${var.app_name}-${data.aws_caller_identity.current.account_id}-dev"
  image_provider_secret_parameter_arns = compact([
    var.fal_key_ssm_parameter_arn,
    var.replicate_api_token_ssm_parameter_arn,
  ])

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
