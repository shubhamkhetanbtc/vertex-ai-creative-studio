#!/bin/bash

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Utility functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    local missing_deps=0
    
    # Check for required tools
    for cmd in gcloud terraform; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is required but not installed."
            missing_deps=1
        fi
    done

    # Check if gcloud is authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
        log_error "Not authenticated with gcloud. Please run 'gcloud auth login' first."
        missing_deps=1
    fi

    if [ $missing_deps -eq 1 ]; then
        log_error "Prerequisites check failed. Please install missing dependencies and try again."
        exit 1
    fi
}

# Check prerequisites before proceeding
log_info "Checking prerequisites..."
check_prerequisites

# Guard against stray impersonation settings in the shell (can break Terraform auth)
if [ -n "${GOOGLE_IMPERSONATE_SERVICE_ACCOUNT:-}" ]; then
    log_warn "Clearing GOOGLE_IMPERSONATE_SERVICE_ACCOUNT (was: $GOOGLE_IMPERSONATE_SERVICE_ACCOUNT)"
    unset GOOGLE_IMPERSONATE_SERVICE_ACCOUNT
fi
log_info "Impersonation env after guard: GOOGLE_IMPERSONATE_SERVICE_ACCOUNT='${GOOGLE_IMPERSONATE_SERVICE_ACCOUNT:-}'"

# Set region and project
export REGION=us-central1
export PROJECT_ID=$(gcloud config get-value project)
export INITIAL_USER=shubham.khetan@buildthe.cloud

log_info "Using project: $PROJECT_ID"
log_info "Using region: $REGION"
log_info "Initial user: $INITIAL_USER"

# Create tfvars file

if [ ! -f terraform.tfvars ]; then
  cat > terraform.tfvars << EOF
project_id = "$PROJECT_ID"
initial_user = "$INITIAL_USER"
use_lb = false
EOF
  echo "terraform.tfvars created."
else
  echo "terraform.tfvars already exists. Skipping creation."
fi

# Run Terraform with error handling
log_info "Initializing Terraform..."
if ! terraform init; then
    log_error "Terraform initialization failed"
    exit 1
fi

# Function to handle Terraform imports
handle_terraform_import() {
    local resource_name="$1"
    local resource_address="$2"
    local resource_id="$3"
    local max_retries=3
    local retry_count=0
    local import_success=false
    
    log_info "Attempting to import $resource_name..."
    
    # Check if resource is already in Terraform state
    if terraform state show "$resource_address" &>/dev/null; then
        log_warn "$resource_name is already in Terraform state, skipping import"
        return 0
    fi
    
    # For storage buckets, verify existence first
    if [[ "$resource_address" == *"google_storage_bucket"* ]]; then
        if gsutil ls -b "gs://$resource_id" &>/dev/null; then
            log_info "Storage bucket $resource_id exists, proceeding with import"
        else
            log_warn "Storage bucket $resource_id does not exist yet, skipping import"
            return 0
        fi
    fi
    
    # Attempt import with retries
    while [ $retry_count -lt $max_retries ]; do
        if terraform import "$resource_address" "$resource_id" 2>/dev/null; then
            log_info "$resource_name successfully imported"
            import_success=true
            break
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -lt $max_retries ]; then
                log_warn "Import attempt $retry_count failed, retrying..."
                sleep 2
            fi
        fi
    done
    
    if [ "$import_success" != "true" ]; then
        log_warn "$resource_name import failed after $max_retries attempts, continuing anyway..."
    fi
    
    # Verify the import
    if terraform state show "$resource_address" &>/dev/null; then
        log_info "Verified $resource_name is now in Terraform state"
    else
        log_warn "Could not verify $resource_name in Terraform state"
    fi
}

# Attempt to import Firestore database if it exists
handle_terraform_import \
    "Firestore database" \
    "google_firestore_database.create_studio_asset_metadata" \
    "projects/$PROJECT_ID/databases/create-studio-asset-metadata"

# Import budgets Firestore database and bootstrap docs if they already exist
handle_terraform_import \
    "Budget Firestore database" \
    "google_firestore_database.budget_allocation" \
    "projects/$PROJECT_ID/databases/creative-studio-budget-allocation"

handle_terraform_import \
    "Budget collection bootstrap doc" \
    "google_firestore_document.budget_collection_bootstrap" \
    "projects/$PROJECT_ID/databases/creative-studio-budget-allocation/documents/budgets/__bootstrap"

handle_terraform_import \
    "Users collection bootstrap doc" \
    "google_firestore_document.users_collection_bootstrap" \
    "projects/$PROJECT_ID/databases/creative-studio-budget-allocation/documents/users/__bootstrap"

# Import service accounts
handle_terraform_import \
    "creative_studio Service account" \
    "google_service_account.creative_studio" \
    "projects/$PROJECT_ID/serviceAccounts/service-creative-studio@$PROJECT_ID.iam.gserviceaccount.com"

handle_terraform_import \
    "cloudbuild Service account" \
    "google_service_account.cloudbuild" \
    "projects/$PROJECT_ID/serviceAccounts/builds-creative-studio@$PROJECT_ID.iam.gserviceaccount.com"

# Import storage resources
handle_terraform_import \
    "Assets Storage Bucket" \
    "google_storage_bucket.assets" \
    "creative-studio-$PROJECT_ID-assets"

handle_terraform_import \
    "Artifact Registry" \
    "google_artifact_registry_repository.creative_studio" \
    "projects/$PROJECT_ID/locations/$REGION/repositories/creative-studio"

# Import Cloud Run Service
handle_terraform_import \
    "Cloud Run Service" \
    "google_cloud_run_v2_service.creative_studio" \
    "projects/$PROJECT_ID/locations/$REGION/services/creative-studio"

# Import and verify Source Storage Bucket
BUCKET_NAME="run-resources-$PROJECT_ID-$REGION"
BUCKET_RESOURCE='module.source_bucket.google_storage_bucket.buckets["run-resources-'$PROJECT_ID'-'$REGION'"]'

# First check if bucket exists
if gsutil ls -b "gs://$BUCKET_NAME" &>/dev/null; then
    log_info "Storage bucket $BUCKET_NAME exists"
    
    # Remove from state if it exists to ensure clean import
    terraform state rm "$BUCKET_RESOURCE" 2>/dev/null || true
    
    # Import the bucket
    handle_terraform_import \
        "Source Storage Bucket" \
        "$BUCKET_RESOURCE" \
        "$BUCKET_NAME"
    
    # Force refresh the state of the module
    log_info "Refreshing Terraform state for source_bucket module..."
    terraform refresh -target="module.source_bucket" || {
        log_warn "State refresh had issues, but continuing..."
    }
else
    log_info "Storage bucket $BUCKET_NAME does not exist yet, will be created by Terraform"
fi

# Import Firestore Indexes
handle_terraform_import \
    "Firestore Index (genmedia library)" \
    "google_firestore_index.genmedia_library_mime_type_timestamp" \
    "projects/$PROJECT_ID/databases/create-studio-asset-metadata/collectionGroups/genmedia/indexes/CICAgJiUsZIK"

handle_terraform_import \
    "Firestore Index (genmedia chooser)" \
    "google_firestore_index.genmedia_chooser_media_type_timestamp" \
    "projects/$PROJECT_ID/databases/create-studio-asset-metadata/collectionGroups/genmedia/indexes/CICAgJiUpoML"

# Run Terraform apply with error handling
log_info "Planning Terraform changes..."
terraform plan -out=tfplan || {
    log_error "Terraform plan failed"
    exit 1
}

log_info "Applying Terraform configuration..."
if ! terraform apply tfplan; then
    # If apply fails, try to refresh state and apply again
    log_warn "Initial apply failed, attempting state refresh and retry..."
    
    # Force refresh the entire state
    terraform refresh
    
    # Try apply again
    if ! terraform apply -auto-approve; then
        log_error "Terraform apply failed after retry"
        exit 1
    else
        log_info "Terraform apply succeeded after retry"
    fi
fi

# Clean up plan file
rm -f tfplan

# Run build script with error handling
log_info "Running build script..."
if ! ./build.sh; then
    log_error "Build script failed"
    exit 1
fi

# Save cloud run URL with error handling
log_info "Retrieving Cloud Run URL..."
APP_URL=$(gcloud run services describe creative-studio \
    --platform=managed \
    --region=$REGION \
    --format='value(status.url)') || {
    log_error "Failed to retrieve Cloud Run URL"
    exit 1
}

# Create temporary file for secret
TEMP_URL_FILE=$(mktemp)
echo "$APP_URL" > "$TEMP_URL_FILE"

# Store URL in Secret Manager with error handling
log_info "Saving Cloud Run URL to Secret Manager..."
if ! gcloud secrets describe cloud-run-app-url >/dev/null 2>&1; then
    log_info "Creating new secret..."
    if ! gcloud secrets create cloud-run-app-url \
        --replication-policy="automatic" \
        --data-file="$TEMP_URL_FILE"; then
        log_error "Failed to create secret"
        rm "$TEMP_URL_FILE"
        exit 1
    fi
else
    log_info "Updating existing secret..."
    if ! gcloud secrets versions add cloud-run-app-url \
        --data-file="$TEMP_URL_FILE"; then
        log_error "Failed to update secret"
        rm "$TEMP_URL_FILE"
        exit 1
    fi
fi

# Clean up temporary file
rm "$TEMP_URL_FILE"

log_info "Cloud Run App URL saved to Secret Manager: $APP_URL"

# Add IAP policy with error handling
log_info "Setting up IAP policy..."
if ! gcloud beta iap web add-iam-policy-binding \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --member="user:$INITIAL_USER" \
    --role="roles/iap.httpsResourceAccessor" \
    --resource-type=cloud-run \
    --service=creative-studio; then
    log_error "Failed to set IAP policy"
    exit 1
fi

log_info "Deployment completed successfully!"
