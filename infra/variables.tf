variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name used for resource names and tags."
  type        = string
  default     = "market-river-generator"
}

variable "bucket_name" {
  description = "S3 bucket for images, metadata, failures, and manifests. Leave empty to use an account-scoped default."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Docker image tag to run from ECR."
  type        = string
  default     = "latest"
}

variable "ecr_max_image_count" {
  description = "Maximum number of container images to retain in ECR."
  type        = number
  default     = 3
}

variable "image_provider" {
  description = "Image provider selected by the application. Use mock, none, future, or fal."
  type        = string
  default     = "mock"
}

variable "fal_key_ssm_parameter_arn" {
  description = "Optional ARN of a SecureString SSM parameter containing FAL_KEY for ECS tasks."
  type        = string
  default     = ""
}

variable "fal_model" {
  description = "fal.ai model endpoint ID used when image_provider is fal."
  type        = string
  default     = "fal-ai/flux/schnell"
}

variable "fal_image_size" {
  description = "fal.ai image size preset used when image_provider is fal."
  type        = string
  default     = "landscape_4_3"
}

variable "fal_output_format" {
  description = "fal.ai output image format used when image_provider is fal."
  type        = string
  default     = "jpeg"
}

variable "fal_num_inference_steps" {
  description = "fal.ai inference step count used when image_provider is fal."
  type        = number
  default     = 4
}

variable "fal_acceleration" {
  description = "fal.ai acceleration setting used when image_provider is fal."
  type        = string
  default     = "none"
}

variable "fal_enable_safety_checker" {
  description = "Enable fal.ai safety checker when image_provider is fal."
  type        = bool
  default     = true
}

variable "public_base_url" {
  description = "Optional public URL prefix for S3 objects, such as a CloudFront distribution URL."
  type        = string
  default     = ""
}

variable "enable_public_read" {
  description = "Allow public read access to generated S3 objects so a website can fetch latest.json directly."
  type        = bool
  default     = true
}

variable "generated_artifact_retention_days" {
  description = "Days to retain generated S3 images, metadata, and failure records."
  type        = number
  default     = 14
}

variable "noncurrent_version_retention_days" {
  description = "Days to retain noncurrent S3 object versions, including older latest.json versions."
  type        = number
  default     = 14
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Fargate task memory in MB."
  type        = number
  default     = 512
}

variable "cpu_architecture" {
  description = "Fargate task CPU architecture. ARM64 is cheaper and matches Apple Silicon Docker builds."
  type        = string
  default     = "ARM64"

  validation {
    condition     = contains(["ARM64", "X86_64"], var.cpu_architecture)
    error_message = "cpu_architecture must be ARM64 or X86_64."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 7
}

variable "vpc_id" {
  description = "Existing VPC ID. Leave empty to create a minimal public VPC."
  type        = string
  default     = ""
}

variable "public_subnet_ids" {
  description = "Existing public subnet IDs. Leave empty to create two public subnets."
  type        = list(string)
  default     = []
}

variable "vpc_cidr" {
  description = "CIDR block used only when creating a new VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks used only when creating new public subnets."
  type        = list(string)
  default     = ["10.42.1.0/24", "10.42.2.0/24"]
}
