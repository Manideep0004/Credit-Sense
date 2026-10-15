###############################################################################
# PostgreSQL RDS Module for CreditSense
###############################################################################

variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "environment" { type = string; default = "production" }
variable "db_password" { type = string; sensitive = true }

resource "aws_db_subnet_group" "db_subnets" {
  name       = "creditsense-${var.environment}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "creditsense-db-subnets"
  }
}

resource "aws_security_group" "rds_sg" {
  name        = "creditsense-${var.environment}-rds-sg"
  description = "Allow inbound PostgreSQL traffic from EKS worker nodes"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL"
    from_port   = 5432
    to_port     = 5432
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

resource "aws_db_instance" "postgres" {
  identifier             = "creditsense-${var.environment}-postgres"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = "db.t4g.small"
  allocated_storage      = 20
  max_allocated_storage  = 100
  storage_type           = "gp3"
  db_name                = "creditsense_db"
  username               = "creditsense_admin"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.db_subnets.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  skip_final_snapshot    = true
  multi_az               = false
  backup_retention_period = 7

  tags = {
    Name        = "creditsense-postgres"
    Environment = var.environment
  }
}

output "endpoint" {
  value = aws_db_instance.postgres.endpoint
}
