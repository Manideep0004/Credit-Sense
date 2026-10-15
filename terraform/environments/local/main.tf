###############################################################################
# CreditSense Terraform - Local / Minikube / Kind Environment
# 100% Free / $0 Cost Local Infrastructure Definition
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

# ── CreditSense Namespace ───────────────────────────────────────────────────
resource "kubernetes_namespace" "creditsense" {
  metadata {
    name = "creditsense"
    labels = {
      environment = "local-dev"
      project     = "creditsense"
    }
  }
}

# ── KEDA Helm Release ───────────────────────────────────────────────────────
resource "helm_release" "keda" {
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  namespace        = "keda"
  create_namespace = true
  version          = "2.12.0"
}

# ── Prometheus Community Helm Release (Local Observability) ─────────────────
resource "helm_release" "prometheus_stack" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true
  version          = "51.2.0"

  set {
    name  = "grafana.adminPassword"
    value = "admin"
  }
}
