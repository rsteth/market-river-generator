output "bucket_name" {
  description = "S3 bucket used for generated assets and manifests."
  value       = aws_s3_bucket.assets.bucket
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.app.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.app.arn
}

output "task_definition_arn" {
  description = "Current ECS task definition ARN."
  value       = aws_ecs_task_definition.app.arn
}

output "task_security_group_id" {
  description = "Security group ID used by scheduled tasks."
  value       = aws_security_group.task.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs used by scheduled tasks."
  value       = local.subnet_ids
}

output "scheduler_names" {
  description = "EventBridge Scheduler schedule names."
  value       = { for slot, schedule in aws_scheduler_schedule.market_slots : slot => schedule.name }
}

output "latest_manifest_url" {
  description = "Default S3 URL for latest.json. Use PUBLIC_BASE_URL if configured."
  value       = var.public_base_url != "" ? "${trim(var.public_base_url, "/")}/manifests/latest.json" : "https://${aws_s3_bucket.assets.bucket}.s3.${var.aws_region}.amazonaws.com/manifests/latest.json"
}

