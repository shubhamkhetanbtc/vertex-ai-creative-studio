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
    for cmd in gcloud terraform git; do
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

    # Check if git is configured
    if ! git config user.email &> /dev/null; then
        log_warn "Git user email is not configured. Some operations might fail."
    fi

    if [ $missing_deps -eq 1 ]; then
        log_error "Prerequisites check failed. Please install missing dependencies and try again."
        exit 1
    fi
}

# Check prerequisites before proceeding
log_info "Checking prerequisites..."
check_prerequisites

# Prompt for user input with validation
while true; do
    read -p "Enter the initial user email (e.g., user@example.com): " INITIAL_USER
    if [[ "$INITIAL_USER" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        break
    else
        log_error "Invalid email format. Please try again."
    fi
done

# Set region and project
export REGION=us-central1
export PROJECT_ID=$(gcloud config get-value project)

log_info "Using project: $PROJECT_ID"
log_info "Using region: $REGION"
log_info "Initial user: $INITIAL_USER"

# Clone and setup repository
REPO_NAME="vertex-ai-creative-studio"
REPO_URL="https://github.com/buildthecloudpwc/vertex-ai-creative-studio.git"

if [ ! -d "$REPO_NAME" ]; then
    log_info "Cloning repository..."
    if ! git clone "$REPO_URL"; then
        log_error "Failed to clone repository"
        exit 1
    fi
else
    log_info "Repository already exists, checking for updates..."
    (cd "$REPO_NAME" && git fetch && git status)
fi

cd "$REPO_NAME" || {
    log_error "Failed to change directory to $REPO_NAME"
    exit 1
}

# Create tfvars file with error handling
if [ ! -f terraform.tfvars ]; then
    log_info "Creating terraform.tfvars file..."
    cat > terraform.tfvars << EOF || {
        log_error "Failed to create terraform.tfvars"
        exit 1
    }
project_id = "$PROJECT_ID"
initial_user = "$INITIAL_USER"
use_lb = false
EOF
    log_info "terraform.tfvars created successfully"
else
    log_warn "terraform.tfvars already exists. Skipping creation."
    log_info "Current terraform.tfvars content:"
    cat terraform.tfvars
fi

# Function to handle Terraform imports
handle_terraform_import() {
    local resource_name="$1"
    local resource_address="$2"
    local resource_id="$3"
    
    log_info "Attempting to import $resource_name..."
    if terraform import "$resource_address" "$resource_id" 2>/dev/null; then
        log_info "$resource_name successfully imported"
    else
        log_warn "$resource_name does not exist yet or is already managed by Terraform, skipping import"
    fi
}

# Run Terraform with error handling
log_info "Initializing Terraform..."
if ! terraform init; then
    log_error "Terraform initialization failed"
    exit 1
fi

# Import all resources
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

handle_terraform_import \
    "creative_studio Service account" \
    "google_service_account.creative_studio" \
    "projects/$PROJECT_ID/serviceAccounts/service-creative-studio@$PROJECT_ID.iam.gserviceaccount.com"

handle_terraform_import \
    "cloudbuild Service account" \
    "google_service_account.cloudbuild" \
    "projects/$PROJECT_ID/serviceAccounts/builds-creative-studio@$PROJECT_ID.iam.gserviceaccount.com"

handle_terraform_import \
    "Assets Storage Bucket" \
    "google_storage_bucket.assets" \
    "creative-studio-$PROJECT_ID-assets"

handle_terraform_import \
    "Artifact Registry" \
    "google_artifact_registry_repository.creative_studio" \
    "projects/$PROJECT_ID/locations/$REGION/repositories/creative-studio"

handle_terraform_import \
    "Cloud Run Service" \
    "google_cloud_run_v2_service.creative_studio" \
    "projects/$PROJECT_ID/locations/$REGION/services/creative-studio"

handle_terraform_import \
    "Source Storage Bucket" \
    'module.source_bucket.google_storage_bucket.buckets["run-resources-$PROJECT_ID-$REGION"]' \
    "run-resources-$PROJECT_ID-$REGION"

handle_terraform_import \
    "Firestore Index (genmedia library)" \
    "google_firestore_index.genmedia_library_mime_type_timestamp" \
    "projects/$PROJECT_ID/databases/create-studio-asset-metadata/collectionGroups/genmedia/indexes/CICAgJiUsZIK"

handle_terraform_import \
    "Firestore Index (genmedia chooser)" \
    "google_firestore_index.genmedia_chooser_media_type_timestamp" \
    "projects/$PROJECT_ID/databases/create-studio-asset-metadata/collectionGroups/genmedia/indexes/CICAgJiUpoML"

# Run Terraform apply with error handling
log_info "Applying Terraform configuration..."
if ! terraform apply -auto-approve; then
    log_error "Terraform apply failed"
    exit 1
fi

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
log_info "Deployment completed successfully!"

# Add IAP policy
gcloud beta iap web add-iam-policy-binding \
--project=$PROJECT_ID \
--region=$REGION \
--member="user:$INITIAL_USER" \
--role="roles/iap.httpsResourceAccessor" \
--resource-type=cloud-run \
--service=creative-studio

echo "Deployment complete!"
