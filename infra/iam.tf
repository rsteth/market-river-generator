data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.app_name}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  count = length(local.image_provider_secret_parameter_arns) == 0 ? 0 : 1

  statement {
    sid = "ReadImageProviderSecrets"
    actions = [
      "ssm:GetParameters",
    ]
    resources = local.image_provider_secret_parameter_arns
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  count = length(local.image_provider_secret_parameter_arns) == 0 ? 0 : 1

  name   = "${var.app_name}-execution-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets[0].json
}

resource "aws_iam_role" "task" {
  name               = "${var.app_name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "task_s3" {
  statement {
    sid = "ListBucket"
    actions = [
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.assets.arn]
  }

  statement {
    sid = "ReadWriteGeneratedObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "${aws_s3_bucket.assets.arn}/images/*",
      "${aws_s3_bucket.assets.arn}/metadata/*",
      "${aws_s3_bucket.assets.arn}/manifests/*",
      "${aws_s3_bucket.assets.arn}/pipeline-runs/*",
      "${aws_s3_bucket.assets.arn}/failures/*",
      "${aws_s3_bucket.assets.arn}/prompts/*",
    ]
  }
}

resource "aws_iam_role_policy" "task_s3" {
  name   = "${var.app_name}-s3"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_s3.json
}

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.app_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid     = "RunTask"
    actions = ["ecs:RunTask"]

    resources = [
      aws_ecs_task_definition.app.arn,
      "${replace(aws_ecs_task_definition.app.arn, "/:\\d+$/", "")}:*",
    ]
  }

  statement {
    sid     = "PassTaskRoles"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.task.arn,
      aws_iam_role.task_execution.arn,
    ]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.app_name}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
