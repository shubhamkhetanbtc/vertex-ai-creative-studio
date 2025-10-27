/**
* Copyright 2024 Google LLC
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*     http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

variable "project_id" {
  type = string
}

variable "region" {
  description = "Location for load balancer and Cloud Run resources"
  type        = string
  default     = "us-central1"
}

variable "use_lb" {
  description = "Run load balancer on HTTPS and provision managed certificate with provided `domain`."
  type        = bool
  default     = true
}

variable "domain" {
  description = "Domain name to run the load balancer on. Used if `ssl` is `true`."
  type        = string
  default     = ""
}

variable "initial_container_image" {
  description = "Container image to use for the Cloud Run service hosting Creative Studio. Because infra is deployed through Terraform this defaults to placeholder image; however, if you are applying Terraform template post initial deployment, use the latest built image to avoid reverting back to the placeholder."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/placeholder"
}

variable "model_id" {
  description = "Veo model ID to use for video generation"
  type        = string
  default     = "gemini-2.5-flash"
}

variable "veo_model_id" {
  description = "Veo model ID to use for video generation"
  type        = string
  default     = "veo-3.0-generate-001"
}

variable "veo_exp_model_id" {
  description = "Experimental Veo model ID to use for video generation"
  type        = string
  default     = "veo-3.0-generate-preview"
}

variable "lyria_model_id" {
  description = "Lyria model ID to use for audio generation"
  type        = string
  default     = "lyria-002"
}

variable "edit_images_enabled" {
  description = "Feature flag for Edit Images feature"
  type        = bool
  default     = true
}

variable "enable_data_deletion" {
  description = "Whether to allow force destroy on storage buckets. Should be false in production."
  type        = bool
  default     = false # Default to safe
}

variable "initial_user" {
  description = "Email address of initial user that will be granted access to Creative Studio in IAP"
  type        = string
  nullable    = true
  default     = null
}

variable "allow_local_domain_cors_requests" {
  description = "Whether to allow local domain requests to the assets GCS bucket"
  type        = bool
  default     = false
}

variable "sleep_time" {
  description = "Amount of time to wait post service API enablement to allow for eventual consistency to trickly through GCP."
  type        = number
  default     = 45
}

# Application environment ("", "local", "dev", "prod")
variable "app_env" {
  description = "Application environment label used by the app for behavior toggles."
  type        = string
  default     = ""
}

# Budget enforcement toggle
variable "budget_check_enabled" {
  description = "Enable budget checks and gating."
  type        = bool
  default     = true
}

# Firestore DB and collections used for budgets feature
variable "budget_db_id" {
  description = "Firestore database ID for budgets and users collections."
  type        = string
  default     = "creative-studio-budget-allocation"
}

variable "budget_users_collection" {
  description = "Firestore collection name for users to store department mapping."
  type        = string
  default     = "users"
}

variable "budgets_collection" {
  description = "Firestore collection name for department budgets."
  type        = string
  default     = "budgets"
}

# BigQuery billing export identifiers (optional; if unset, cost will be unavailable)
variable "billing_project_id" {
  description = "Project ID that hosts the BigQuery billing export (defaults to service project if not provided)."
  type        = string
  default     = null
}

variable "billing_dataset" {
  description = "BigQuery dataset for the billing export."
  type        = string
  default     = null
}

variable "billing_table" {
  description = "BigQuery table for the billing export (e.g., gcp_billing_export)."
  type        = string
  default     = null
}

# Optional analytics
variable "ga_measurement_id" {
  description = "Google Analytics measurement ID (optional)."
  type        = string
  default     = null
}
