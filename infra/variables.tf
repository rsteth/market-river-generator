variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-west-2"
}

variable "app_name" {
  description = "Application name used for resource names and tags."
  type        = string
  default     = "market-river-generator"
}

variable "bucket_name" {
  description = "S3 bucket for images, metadata, failures, and manifests."
  type        = string
  default     = "stethem-market-river-dev"
}

variable "image_tag" {
  description = "Docker image tag to run from ECR."
  type        = string
  default     = "latest"
}

variable "image_provider" {
  description = "Image provider selected by the application. Use mock or none for the MVP."
  type        = string
  default     = "mock"
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

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory in MB."
  type        = number
  default     = 1024
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

