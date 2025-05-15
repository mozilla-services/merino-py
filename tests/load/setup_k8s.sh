#!/bin/bash
set -eu

# Declare variables
GCLOUD=$(which gcloud)
SED=$(which sed)
KUBECTL=$(which kubectl)
GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
REPOSITORY_ID='merino'
IMAGE_NAME='locust-merino'
CLUSTER='merino-locust-load-test'
TARGET='https://stagepy.merino.nonprod.cloudops.mozgcp.net'
SCOPE='https://www.googleapis.com/auth/cloud-platform'
REGION='us-west1'
WORKER_COUNT=5 # Default worker count
MACHINE_TYPE='n1-standard-2' # 2 CPUs + 7.50GB Memory
DIRECTORY=$(pwd)

MERINO_DIRECTORY=$DIRECTORY/tests/load/kubernetes-config
MASTER_FILE=locust-master-controller.yml
WORKER_FILE=locust-worker-controller.yml
SERVICE_FILE=locust-master-service.yml
DAEMONSET_FILE=locust-worker-daemonset.yml
WORKER_KUBELET_CONFIG_FILE=worker-kubelet-config.yml

LOCUST_IMAGE_TAG=$(git log -1 --pretty=format:%h)
echo "Docker image tag for locust is set to: ${LOCUST_IMAGE_TAG}"

# Declare variables to be replaced later in the YAML file using the sed commands
ENVIRONMENT_VARIABLES=(
  "TARGET_HOST,$TARGET"
  'LOCUST_CSV,merino'
  "LOCUST_HOST,$TARGET"
  'MERINO_REMOTE_SETTINGS__SERVER,https://firefox.settings.services.mozilla.com'
  'MERINO_REMOTE_SETTINGS__COLLECTION,quicksuggest-other'
  'MERINO_REMOTE_SETTINGS__BUCKET,main'
  'MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH,dev/top_picks.json'
  'MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT,"4"'
  'MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT,"2"'
  'MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY,'
  'MERINO_PROVIDERS__WIKIPEDIA__ES_URL,https://merino-nonprod.es.us-west1.gcp.cloud.es.io:9243'
  'MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX,enwiki-v1'
)

# Usage function
usage() {
    echo "Usage: $0 {create|setup|delete} [smoke|average]"
    echo "Note: The shape parameter is only required for 'create' and 'setup' operations."
    exit 1
}

# Validate and set operation and shape parameters
set_params() {
    local response=$1
    local shape=${2:-smoke}

    case $response in
        create|setup)
            case $shape in
                smoke)
                    WORKER_COUNT=5
                    ;;
                average)
                    WORKER_COUNT=25
                    ;;
                *)
                    echo -e "==================== Invalid shape! Please choose 'smoke' or 'average'."
                    usage
                    ;;
            esac
            ;;
        delete)
            ;;
        *)
            echo -e "==================== Invalid operation! Please choose 'create', 'setup', or 'delete'."
            usage
            ;;
    esac

    OPERATION=$response
}

SetEnvironmentVariables() {
  local filePath=$1
  for e in "${ENVIRONMENT_VARIABLES[@]}"
  do
      IFS="," read -r name value <<< "$e"
      if [ -z "$value" ]; then
        echo -e "\033[33mWARNING! The $name environment variable is undefined\033[0m"
        continue
      fi
      $SED -i -e "/name: $name/{n; s|value:.*|value: $value|}" "$filePath"
  done
}

SetupGksCluster() {
    # Configure Kubernetes
    echo -e "==================== Prepare environments with set of environment variables "
    echo -e "==================== Set Kubernetes Cluster "
    export CLUSTER=$CLUSTER
    echo -e "==================== Set Kubernetes TARGET "
    export TARGET=$TARGET
    echo -e "==================== Set SCOPE "
    export SCOPE=$SCOPE

    echo -e "==================== Refresh Kubeconfig at path ~/.kube/config "
    $GCLOUD container clusters get-credentials $CLUSTER --region $REGION --project "$GOOGLE_CLOUD_PROJECT"

    # Build Docker Images
    echo -e "==================== Build the Docker image and store it in your project's artifact registry. Tag with the latest commit hash "
    $GCLOUD builds submit --config=./tests/load/cloudbuild.yaml --substitutions=TAG_NAME="$LOCUST_IMAGE_TAG"
    echo -e "==================== Verify that the Docker image is in your project's artifact registry repository"
    $GCLOUD artifacts docker tags list "$REGION-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/$REPOSITORY_ID/$IMAGE_NAME" | grep $LOCUST_IMAGE_TAG

    # Deploying the Locust master and worker nodes
    echo -e "==================== Update Kubernetes Manifests "
    echo -e "==================== Replace the target host and project ID with the deployed endpoint and project ID in the locust-master-controller.yml and locust-worker-controller.yml files"

    $SED -i -e "s|replicas:.*|replicas: $WORKER_COUNT|" "$MERINO_DIRECTORY/$WORKER_FILE"
    for file in $MASTER_FILE $WORKER_FILE
    do
        $SED -i -e "s|image:.*|image: $REGION-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/$REPOSITORY_ID/$IMAGE_NAME:$LOCUST_IMAGE_TAG|" "$MERINO_DIRECTORY/$file"
        SetEnvironmentVariables "$MERINO_DIRECTORY/$file"
    done

    # Deploy the Locust master and worker nodes using Kubernetes Manifests
    echo -e "==================== Deploy the Locust master and worker nodes"
    $KUBECTL apply -f "$MERINO_DIRECTORY/$MASTER_FILE"
    $KUBECTL apply -f "$MERINO_DIRECTORY/$SERVICE_FILE"
    $KUBECTL apply -f "$MERINO_DIRECTORY/$WORKER_FILE"
    $KUBECTL apply -f "$MERINO_DIRECTORY/$DAEMONSET_FILE"

    echo -e "==================== Verify the Locust deployments & Services"
    $KUBECTL get pods -o wide
    $KUBECTL get services
}

# Validate and set parameters
if [[ $# -eq 0 ]]; then
    read -r -p "Enter operation (create/setup/delete): " response
    if [[ $response != "delete" ]]; then
        read -r -p "Enter shape (smoke/average): " shape
    else
        shape=""
    fi
else
    response=$1
    shape=${2:-smoke}
fi

set_params "$response" "$shape"

# Main operation
case $OPERATION in
    create)
        echo -e "==================== Creating the GKE cluster "
        $GCLOUD container clusters create $CLUSTER --region $REGION --scopes $SCOPE --enable-autoscaling --scopes=logging-write,storage-ro --machine-type=$MACHINE_TYPE --addons HorizontalPodAutoscaling,HttpLoadBalancing --enable-dataplane-v2
        $GCLOUD container node-pools create locust-workers --cluster=$CLUSTER --region $REGION --node-labels=node-pool=locust-workers --enable-autoscaling --total-min-nodes=1 --total-max-nodes=30 --scopes=$SCOPE,logging-write,storage-ro --machine-type=$MACHINE_TYPE --system-config-from-file=$MERINO_DIRECTORY/$WORKER_KUBELET_CONFIG_FILE
        SetupGksCluster
        ;;
    delete)
        echo -e "==================== Deleting the GKE cluster "
        $GCLOUD container clusters delete $CLUSTER --region $REGION
        ;;
    setup)
        echo -e "==================== Setting up the GKE cluster "
        SetupGksCluster
        ;;
    *)
        echo -e "==================== Invalid operation! Please choose 'create', 'setup', or 'delete'."
        usage
        ;;
esac
