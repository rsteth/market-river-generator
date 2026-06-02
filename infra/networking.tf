data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  create_network = var.vpc_id == "" || length(var.public_subnet_ids) == 0
  vpc_id         = local.create_network ? aws_vpc.app[0].id : var.vpc_id
  subnet_ids     = local.create_network ? aws_subnet.public[*].id : var.public_subnet_ids
}

resource "aws_vpc" "app" {
  count = local.create_network ? 1 : 0

  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${var.app_name}-vpc"
  })
}

resource "aws_internet_gateway" "app" {
  count = local.create_network ? 1 : 0

  vpc_id = aws_vpc.app[0].id

  tags = merge(local.common_tags, {
    Name = "${var.app_name}-igw"
  })
}

resource "aws_subnet" "public" {
  count = local.create_network ? length(var.public_subnet_cidrs) : 0

  vpc_id                  = aws_vpc.app[0].id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.app_name}-public-${count.index + 1}"
  })
}

resource "aws_route_table" "public" {
  count = local.create_network ? 1 : 0

  vpc_id = aws_vpc.app[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app[0].id
  }

  tags = merge(local.common_tags, {
    Name = "${var.app_name}-public"
  })
}

resource "aws_route_table_association" "public" {
  count = local.create_network ? length(aws_subnet.public) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_security_group" "task" {
  name        = "${var.app_name}-task"
  description = "Scheduled Fargate task egress only."
  vpc_id      = local.vpc_id

  egress {
    description = "HTTPS outbound for yfinance, S3, ECR, and CloudWatch APIs."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.app_name}-task"
  })
}

