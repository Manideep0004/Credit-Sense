variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "db_password" {
  type        = string
  description = "PostgreSQL RDS Master Password"
  sensitive   = true
  default     = "ChangeMeInProdSecure123!"
}
