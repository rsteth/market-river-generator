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
  description = "Image provider selected by the application. Use mock, none, future, fal, or replicate."
  type        = string
  default     = "mock"

  validation {
    condition     = contains(["mock", "none", "future", "fal", "replicate"], var.image_provider)
    error_message = "image_provider must be mock, none, future, fal, or replicate."
  }
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
  default     = "square_hd"
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

variable "replicate_api_token_ssm_parameter_arn" {
  description = "Optional ARN of a SecureString SSM parameter containing REPLICATE_API_TOKEN for ECS tasks."
  type        = string
  default     = ""
}

variable "replicate_model" {
  description = "Replicate model identifier used when image_provider is replicate."
  type        = string
  default     = "black-forest-labs/flux-2-pro"
}

variable "replicate_aspect_ratio" {
  description = "Replicate aspect ratio used when image_provider is replicate."
  type        = string
  default     = "1:1"
}

variable "replicate_resolution" {
  description = "Replicate output resolution used when image_provider is replicate."
  type        = string
  default     = "1 MP"
}

variable "replicate_output_format" {
  description = "Replicate output image format used when image_provider is replicate."
  type        = string
  default     = "webp"
}

variable "replicate_output_quality" {
  description = "Replicate output quality used when image_provider is replicate."
  type        = number
  default     = 88
}

variable "replicate_safety_tolerance" {
  description = "Replicate safety tolerance used when image_provider is replicate. 1 is most strict, 5 is most permissive."
  type        = number
  default     = 2
}

variable "replicate_seed" {
  description = "Optional Replicate seed. Leave null for random generation."
  type        = number
  default     = null
}

variable "prompt_active_key" {
  description = "S3 object key for the active prompt registry pointer."
  type        = string
  default     = "prompts/river_city/active.json"
}

variable "allow_bundled_prompt_fallback" {
  description = "Allow ECS runs to use the bundled prompt if the S3 prompt registry cannot be loaded."
  type        = bool
  default     = false
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
  default     = 30
}

variable "noncurrent_version_retention_days" {
  description = "Days to retain noncurrent S3 object versions, including older latest.json versions."
  type        = number
  default     = 30
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
