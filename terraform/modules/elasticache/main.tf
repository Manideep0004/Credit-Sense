###############################################################################
# Redis ElastiCache Module for CreditSense Task Queue
###############################################################################

variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "environment" { type = string; default = "production" }

resource "aws_elasticache_subnet_group" "redis_subnets" {
  name       = "creditsense-${var.environment}-redis-subnets"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "redis_sg" {
  name        = "creditsense-${var.environment}-redis-sg"
  description = "Allow inbound Redis traffic from EKS worker nodes"
  vpc_id      = var.vpc_id

  ingress {
    description = "Redis"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "creditsense-${var.environment}-redis"
  description                   = "Redis cluster for CreditSense Celery broker and result backend"
  node_type                     = "cache.t4g.micro"
  num_cache_clusters            = 1
  port                          = 6379
  parameter_group_name          = "default.redis7"
  subnet_group_name             = aws_elasticache_subnet_group.redis_subnets.name
  security_group_ids            = [aws_security_group.redis_sg.id]
  at_rest_encryption_enabled   = true
  transit_encryption_enabled   = false

  tags = {
    Name        = "creditsense-redis"
    Environment = var.environment
  }
}

output "primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}
