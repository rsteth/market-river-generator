resource "aws_s3_bucket" "assets" {
  bucket = local.bucket_name

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id

  rule {
    id     = "expire-generated-images"
    status = "Enabled"

    filter {
      prefix = "images/"
    }

    expiration {
      days = var.generated_artifact_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  rule {
    id     = "expire-generated-metadata"
    status = "Enabled"

    filter {
      prefix = "metadata/"
    }

    expiration {
      days = var.generated_artifact_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  rule {
    id     = "expire-failure-records"
    status = "Enabled"

    filter {
      prefix = "failures/"
    }

    expiration {
      days = var.generated_artifact_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  rule {
    id     = "expire-pipeline-run-records"
    status = "Enabled"

    filter {
      prefix = "pipeline-runs/"
    }

    expiration {
      days = var.generated_artifact_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  rule {
    id     = "expire-old-manifest-versions"
    status = "Enabled"

    filter {
      prefix = "manifests/"
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.assets]
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = aws_s3_bucket.assets.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = !var.enable_public_read
  restrict_public_buckets = !var.enable_public_read
}

resource "aws_s3_bucket_cors_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

data "aws_iam_policy_document" "public_read" {
  count = var.enable_public_read ? 1 : 0

  statement {
    sid     = "PublicReadGeneratedObjects"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = [
      "${aws_s3_bucket.assets.arn}/images/*",
      "${aws_s3_bucket.assets.arn}/metadata/*",
      "${aws_s3_bucket.assets.arn}/manifests/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "public_read" {
  count  = var.enable_public_read ? 1 : 0
  bucket = aws_s3_bucket.assets.id
  policy = data.aws_iam_policy_document.public_read[0].json

  depends_on = [aws_s3_bucket_public_access_block.assets]
}
