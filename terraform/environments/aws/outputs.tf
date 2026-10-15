output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "database_endpoint" {
  description = "PostgreSQL RDS connection endpoint"
  value       = module.rds.endpoint
}

output "redis_endpoint" {
  description = "Redis ElastiCache connection endpoint"
  value       = module.elasticache.primary_endpoint
}
