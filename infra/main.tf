locals {
  common_tags = {
    App = var.app_name
  }

  container_name = var.app_name

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

