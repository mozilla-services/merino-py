# Merino Load (Locust) Tests

This documentation describes the load tests for Merino.
This test framework uses IP2Location LITE data available from https://lite.ip2location.com

## Overview

The tests in the `tests/load` directory spawn multiple HTTP clients that consume Merino's API,
in order to simulate real-world load on the Merino infrastructure.
These tests use the Locust framework and are triggered at the discretion of the Merino Engineering Team.

## Related Documentation

* [Merino Load Test Plan][merino_test_plan]
* [Merino Load Test History][merino_history_doc]
* [Merino Load Test Spreadsheet][merino_spreadsheet]

## Local Execution

Note that if you make changes to the load test code, you must stop and remove the Docker containers and networks for changes to reflect.
Do this by running `make load-tests-clean`.

Follow the steps bellow to execute the load tests locally:

### Setup Environment

#### 1. Configure Environment Variables

The following environment variables as well as
[Locust environment variables][locust_environment_variables] can be set in
`tests\load\docker-compose.yml`.
Make sure any required API key is added but then not checked into source control.

**WARNING**: if the `WIKIPEDIA__ES_API_KEY` is missing, the load tests will not execute.

| Environment Variable                             | Node(s)         | Description                                                                               |
|--------------------------------------------------|-----------------|-------------------------------------------------------------------------------------------|
| LOAD_TESTS__LOGGING_LEVEL                        | master & worker | Level for the logger in the load tests as an int (`10` for `DEBUG`, `20` for `INFO` etc.) |
| MERINO_REMOTE_SETTINGS__SERVER                   | master & worker | Server URL of the Kinto instance containing suggestions                                   |
| MERINO_REMOTE_SETTINGS__BUCKET                   | master & worker | Kinto bucket with the suggestions                                                         |
| MERINO_REMOTE_SETTINGS__COLLECTION               | master & worker | Kinto collection with the suggestions                                                     |
| MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH | master & worker | The minimum character limit set for long domain suggestion indexing                       |
| MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT    | master & worker | The minimum character limit set for short domain suggestion indexing                      |
| MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT  | master & worker | File path to the json file of domains                                                     |
| MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY          | master & worker | The base64 key used to authenticate on the Elasticsearch cluster specified by es_cloud_id |
| MERINO_PROVIDERS__WIKIPEDIA__ES_URL              | master & worker | The Cloud ID of the Elasticsearch cluster                                                 |
| MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX            | master & worker | The index identifier of Wikipedia in Elasticsearch                                        |                                                                                          |

#### 2. Host Locust via Docker

Execute the following from the repository root:
```shell
make load-tests
```

#### 3. (Optional) Host Merino Locally

Use one of the following commands to host Merino locally. Execute the following from the
repository root:

- Option 1: Use the local development instance
  ```shell
  make dev
  ```
- Option 2: Use the profiler instance
  ```shell
  make profile
  ```
- Option 3: Use the Docker instance
  ```shell
  make docker-build && docker run -p 8000:8000 app:build
  ```

### Run Test Session

#### 1. Start Load Test

* In a browser navigate to `http://localhost:8089/`
* Set up the load test parameters:
    * Option 1: Select the `MerinoSmokeLoadTestShape` or `MerinoAverageLoadTestShape`
      * These options have pre-defined settings
    * Option 2: Select the `Default` load test shape with the following recommended settings:
      * Number of users: 25
      * Spawn rate: 1
      * Host: 'https://merino.services.allizom.org'
        * Set host to 'http://host.docker.internal:8000' to test against a local instance of Merino
      * Duration (Optional): 10m
* Select "Start Swarming"

#### 2. Stop Load Test

Select the 'Stop' button in the top right hand corner of the Locust UI, after the
desired test duration has elapsed. If the 'Run time' is set in step 1, the load test
will stop automatically.

#### 3. Analyse Results

* See [Distributed GCP Execution (Manual Trigger) - Analyse Results](#3-analyse-results-1)
* Only client-side measures, provided by Locust, are available when executing against a
  local instance of Merino.

### Clean-up Environment

#### 1. Remove Load Test Docker Containers

Execute the following from the repository root:
```shell
make load-tests-clean
```

## Distributed GCP Execution - Manual Trigger

Follow the steps bellow to execute the distributed load tests on GCP with a manual trigger:

### Setup Environment

#### 1. Start a GCP Cloud Shell

The load tests can be executed from the [contextual-services-test-eng cloud shell][cloud].

#### 2. Configure the Bash Script

* The `setup_k8s.sh` file, located in the `tests\load` directory, contains shell
commands to **create** a GKE cluster, **setup** an existing GKE cluster or **delete**
a GKE cluster
  * Modify the script to include the MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY
    environment variables
  * Execute the following from the root directory, to make the file executable:
    ```shell
    chmod +x tests/load/setup_k8s.sh
    ```

#### 3. Create the GCP Cluster

* Execute the `setup_k8s.sh` file and select the **create** option, in order to
  initiate the process of creating a cluster, setting up the env variables and
  building the docker image. Choose smoke or average depending on the type
  of load test required.
  ```shell
  ./tests/load/setup_k8s.sh create [smoke|average]
  ```
  * Smoke - The smoke load test verifies the system's performance under minimal load. The test is
    run for a short period, possibly in CD, to ensure the system is working correctly.
  * Average - The average load test measures the system's performance under standard operational conditions.
    The test is meant to reflect an ordinary day in production.
* The cluster creation process will take some time. It is considered complete, once
  an external IP is assigned to the `locust_master` node. Monitor the assignment via
  a watch loop:
  ```bash
  kubectl get svc locust-master --watch
  ```
* The number of workers is defaulted to 5, but can be modified with the
  `kubectl scale` command. Example (10 workers):
  ```bash
  kubectl scale deployment/locust-worker --replicas=10
  ```
* To apply new changes to an existing GCP Cluster, execute the `setup_k8s.sh` file and select the
  **setup** option.
    * This option will consider the local commit history, creating new containers and
      deploying them (see [Artifact Registry][artifact_registry])

### Run Test Session

#### 1. Start Load Test

* In a browser navigate to `http://$EXTERNAL_IP:8089`

  This url can be generated via command
  ```bash
  EXTERNAL_IP=$(kubectl get svc locust-master -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
  echo http://$EXTERNAL_IP:8089
  ```
* Select the `MerinoSmokeLoadTestShape`, this option has pre-defined settings and will last 5 minutes
* Select "Start Swarming"

#### 2. Stop Load Test

Select the 'Stop' button in the top right hand corner of the Locust UI, after the
desired test duration has elapsed. If the 'Run time' is set in step 1, the load test
will stop automatically.

#### 3. Analyse Results

**RPS**
* The request-per-second load target for Merino is `1500`
* Locust reports client-side RPS via the "merino_stats.csv" file and the UI
  (under the "Statistics" tab or the "Charts" tab)
* [Grafana][grafana] reports the server-side RPS via the
  "HTTP requests per second per country" chart

**HTTP Request Failures**
* The number of responses with errors (5xx response codes) should be `0`
* Locust reports Failures via the "merino_failures.csv" file and the UI
  (under the "Failures" tab or the "Charts" tab)
* [Grafana][grafana] reports Failures via the "HTTP Response codes" chart and the
  "HTTP 5xx error rate" chart

**Exceptions**
* The number of exceptions raised by the test framework should be `0`
* Locust reports Exceptions via the "merino_exceptions.csv" file and the UI
  (under the "Exceptions" tab)

**Latency**
* The HTTP client-side response time (aka request duration) for 95 percent of users
  is required to be 200ms or less (`p95 <= 200ms`), excluding weather requests
* Locust reports client-side latency via the "merino_stats.csv" file and the UI
  (under the "Statistics" tab or the "Charts" tab)
  * _Warning!_ A Locust worker with too many users will bottleneck RPS and inflate
    client-side latency measures. Locust reports worker CPU and memory usage metrics via
    the UI (under the "Workers" tab)
* [Grafana][grafana] reports server-side latency via the "p95 latency" chart

**Resource Consumption**
* To conserve costs, resource allocation must be kept to a minimum. It is expected that
  container, CPU and memory usage should trend consistently between load test runs.
* [Grafana][grafana] reports metrics on resources via the "Container Count",
  "CPU usage time sum" and "Memory usage sum" charts

#### 4. Report Results

* Results should be recorded in the [Merino Load Test Spreadsheet][merino_spreadsheet]
* Optionally, the Locust reports can be saved and linked in the spreadsheet:
  * Download the results via the Locust UI or via command:
      ```bash
      kubectl cp <master-pod-name>:/home/locust/merino_stats.csv merino_stats.csv
      kubectl cp <master-pod-name>:/home/locust/merino_exceptions.csv merino_exceptions.csv
      kubectl cp <master-pod-name>:/home/locust/merino_failures.csv merino_failures.csv
      ```
    The `master-pod-name` can be found at the top of the pod list:
      ```bash
      kubectl get pods -o wide
      ```
  * Upload the files to the [ConServ][conserv] drive and record the links in the
    spreadsheet

### Clean-up Environment

#### 1. Delete the GCP Cluster

Execute the `setup_k8s.sh` file and select the **delete** option
```shell
./tests/load/setup_k8s.sh
```

## Distributed GCP Execution - CI Trigger

The load tests are triggered in CI via [Jenkins][jenkins_load_test], which has a command overriding
the load test Dockerfile entrypoint.

Follow the steps below to execute the distributed load tests on GCP with a CI trigger:

### Run Test Session

#### 1. Execute Load Test

To modify the load testing behavior, you must include a label in your Git commit. This must be the
merge commit on the main branch, since only the most recent commit is checked for the label. The
label format is: `[load test: (abort|skip|warn)]`. Take careful note of correct syntax and spacing
within the label. There are three options for load tests: `abort`, `skip`, and `warn`:

- The `abort` label will prevent a prod deployment if the load test fails\
  Ex. `feat: Add feature ABC [load test: abort].`
- The `skip` label will bypass load testing entirely during deployment\
  Ex. `feat: Add feature LMN [load test: skip].`
- The `warn` label will output a Slack warning if the load test fails but still allow for the
  production deployment\
  Ex. `feat: Add feature XYZ [load test: warn].`

If no label is included in the commit message, the load test will be executed with the `warn`
action.

The commit tag signals load test instructions to Jenkins by modifying the Docker image tag. The
Jenkins deployment workflow first deploys to `stage` and then runs load tests if requested. The
Docker image tag passed to Jenkins appears as follows:
`^(?P<environment>stage|prod)(?:-(?P<task>\w+)-(?P<action>abort|skip|warn))?-(?P<commit>[a-z0-9]+)$`

#### 2. Analyse Results

See [Distributed GCP Execution (Manual Trigger) - Analyse Results](#3-analyse-results-1)

#### 3. Report Results

* Optionally, results can be recorded in the [Merino Load Test Spreadsheet][merino_spreadsheet]. It
  is recommended to do so if unusual behavior is observed during load test execution or if the load
  tests fail.
* The Locust reports can be saved and linked in the spreadsheet. The results are persisted in the
  `/data` directory of the `locust-master-0` pod in the `locust-master` k8s cluster in the GCP
  project of `merino-nonprod`. To access the Locust logs:
    * Open a cloud shell in the [Merino stage environment][merino_gcp_stage]
    * Authenticate by executing the following command:
      ```shell
        gcloud container clusters get-credentials merino-nonprod-v1 \
          --region us-west1 --project moz-fx-merino-nonprod-ee93
      ```
    * Identify the log files needed in the Kubernetes pod by executing the following command, which
      lists the log files along with file creation timestamp when the test was performed. The
      `{run-id}` uniquely identifies each load test run:
      ```bash
        kubectl exec -n locust-merino locust-master-0 -- ls -al /data/
      ```
  * Download the results via the Locust UI or via command:
      ```bash
      kubectl -n locust-merino cp locust-master-0:/data/{run-id}-merino_stats.csv merino_stats.csv
      kubectl -n locust-merino cp locust-master-0:/data/{run-id}-merino_exceptions.csv merino_exceptions.csv
      kubectl -n locust-merino cp locust-master-0:/data/{run-id}-merino_failures.csv merino_failures.csv
      ```
  * Upload the files to the [ConServ][conserv] drive and record the links in the
    spreadsheet

## Calibration

Following the addition of new features, such as a Locust Task or Locust User, or
environmental changes, such as node size or the upgrade of a major dependency like the
python version image, it may be necessary to re-establish the recommended parameters of
the performance test.

| Parameter          | Description                                                                                                                                                                                                      |
|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `WAIT TIME`        | - Changing this cadence will increase or decrease the number of channel subscriptions and notifications sent by a MerinoUser. <br/>- The default is currently in use for the MerinoUser class.                   |
| `TASK WEIGHT`      | - Changing this weight impacts the probability of a task being chosen for execution. <br/>- This value is hardcoded in the task decorators of the MerinoUser class.                                              |
| `USERS_PER_WORKER` | - This value should be set to the maximum number of users a Locust worker can support given CPU and memory constraints. <br/>- This value is hardcoded in the LoadTestShape classes.                             |
| `WORKER_COUNT`     | - This value is derived by dividing the total number of users needed for the performance test by the `USERS_PER_WORKER`. <br>- This value is hardcoded in the LoadTestShape classes and the setup_k8s.sh script. |

* Locust documentation is available for [WAIT TIME][13] and [TASK WEIGHT][14]

## Calibrating for USERS_PER_WORKER

This process is used to determine the number of users that a Locust worker can support.

### Setup Environment

#### 1. Start a GCP Cloud Shell

The load tests can be executed from the [contextual-services-test-eng cloud shell][cloud].
If executing a load test for the first time, the git merino-py repository will need to
be cloned locally.

#### 2. Configure the Bash Script

* The `setup_k8s.sh` file, located in the `tests\load` directory, contains
  shell commands to **create** a GKE cluster, **setup** an existing GKE cluster or
  **delete** a GKE cluster
    * Execute the following from the root directory, to make the file executable:
      ```shell
      chmod +x tests/load/setup_k8s.sh
      ```

#### 3. Create the GCP Cluster

* In the `setup_k8s.sh` script, modify the `WORKER_COUNT` variable to equal `1`
* Execute the `setup_k8s.sh` file from the root directory and select the **create**
  option, in order to initiate the process of creating a cluster, setting up the env
  variables and building the docker image. Choose smoke or average depending on the type
  of load test required.
  ```shell
  ./tests/load/setup_k8s.sh create [smoke|average]
  ```
* The cluster creation process will take some time. It is considered complete, once
  an external IP is assigned to the `locust_master` node. Monitor the assignment via
  a watch loop:
  ```bash
  kubectl get svc locust-master --watch
  ```

### Calibrate

Repeat steps 1 to 3, using a process of elimination, such as the bisection method, to
determine the maximum `USERS_PER_WORKER`. The load tests are considered optimized when
CPU and memory resources are maximally utilized. This step is meant to determine the
maximum user count that a node can accommodate by observing CPU and memory usage while
steadily increasing or decreasing the user count. You can monitor the CPU percentage in
the Locust UI but also in the Kubernetes engine Workloads tab where both memory and CPU
are visualized on charts.

#### 1. Start Load Test

* In a browser navigate to `http://$EXTERNAL_IP:8089`
  This url can be generated via command
  ```bash
  EXTERNAL_IP=$(kubectl get svc locust-master -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
  echo http://$EXTERNAL_IP:8089
  ```
* Set up the load test parameters:
    * ShapeClass: Default
    * UserClasses: MerinoUser
    * Number of users: USERS_PER_WORKER (Consult the [Merino_spreadsheet][merino_spreadsheet] to determine a starting point)
    * Ramp up: RAMP_UP (RAMP_UP = 5/USERS_PER_WORKER)
    * Host: 'https://merino.services.allizom.org'
    * Duration (Optional): 600s
* Select "Start Swarm"

#### 2. Stop Load Test

Select the 'Stop' button in the top right hand corner of the Locust UI, after the
desired test duration has elapsed. If the 'Run time' or 'Duration' is set in step 1,
the load test will stop automatically.

#### 3. Analyse Results

**CPU and Memory Resource Graphs**

* CPU and Memory usage should be less than 90% of the available capacity
    * CPU and Memory Resources can be observed in
      [Google Cloud > Kubernetes Engine > Workloads][kubernetes_panel]

**Log Errors or Warnings**

* Locust will emit errors or warnings if high CPU or memory usage occurs during the
  execution of a load test. The presence of these logs is a strong indication that the
  `USERS_PER_WORKER` count is too high

#### 4. Report Results

See [Distributed GCP Execution (Manual Trigger) - Analyse Results](#3-analyse-results-1)

#### 5. Update Shape and Script Values

* `WORKER_COUNT = MAX_USERS/USERS_PER_WORKER`
    * If `MAX_USERS` is unknown, calibrate to determine `WORKER_COUNT`
* Update the `USERS_PER_WORKER` and `WORKER_COUNT` values in the following files:
    * `\tests\load\locustfiles\smoke_load.py` or `\tests\load\locustfiles\average_load.py`
    * \tests\load\setup_k8s.sh

### Clean-up Environment

See [Distributed GCP Execution (Manual Trigger) - Clean-up Environment](#clean-up-environment)

## Calibrating for WORKER_COUNT

This process is used to determine the number of Locust workers required in order to
generate sufficient load for a test given a SHAPE_CLASS.

### Setup Environment

* See [Distributed GCP Execution (Manual Trigger) - Setup Environment](#setup-environment-1)
* Note that in the `setup_k8s.sh` the maximum number of nodes is set using the
  `total-max-nodes` google cloud option. It may need to be increased if the number of
  workers can't be supported by the cluster.

### Calibrate

Repeat steps 1 to 4, using a process of elimination, such as the bisection method, to
determine the maximum `WORKER_COUNT`. The tests are considered optimized when they
generate the minimum load required to cause node scaling in the the Merino-py Stage
environment. You can monitor the Merino-py pod counts on [Grafana][grafana].

#### 1. Update Shape and Script Values

* Update the `WORKER_COUNT` values in the following files:
    * `\tests\load\locustfiles\smoke_load.py` or `\tests\load\locustfiles\average_load.py`
    * \tests\load\setup_k8s.sh
* Using Git, commit the changes locally

#### 2. Start Load Test

* In a browser navigate to `http://$EXTERNAL_IP:8089`
  This url can be generated via command
  ```bash
  EXTERNAL_IP=$(kubectl get svc locust-master -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
  echo http://$EXTERNAL_IP:8089
  ```
* Set up the load test parameters:
    * ShapeClass: SHAPE_CLASS
    * Host: 'https://merino.services.allizom.org'
* Select "Start Swarm"

#### 3. Stop Load Test

Select the 'Stop' button in the top right hand corner of the Locust UI, after the
desired test duration has elapsed. If the 'Run time', 'Duration' or 'ShapeClass'
are set in step 1, the load test will stop automatically.

#### 4. Analyse Results

**Stage Environment Pod Counts**

* The 'Merino-py Pod Count' should demonstrate scaling during the execution of the load test
  * The pod counts can be observed in [Grafana][grafana]

**CPU and Memory Resources**

* CPU and Memory usage should be less than 90% of the available capacity in the cluster
    * CPU and Memory Resources can be observed in
      [Google Cloud > Kubernetes Engine > Workloads][kubernetes_panel]

#### 5. Report Results

* See [Distributed GCP Execution (Manual Trigger) - Report Results](#4-report-results)

### Clean-up Environment

* See [Distributed GCP Execution (Manual Trigger) - Clean-up Environment](#clean-up-environment-1)

## Maintenance

The load test maintenance schedule cadence is once a quarter and should include
updating the following:

1. [uv][uv] version and python dependencies
    * [ ] [pyproject.toml][pyproject_toml]
    * [ ] [uv.lock][uv_lock]
2. [Docker][docker] artifacts
    * [ ] [Dockerfile][dockerfile]
    * [ ] [docker-compose.yml][docker_compose]
3. Distributed GCP execution scripts and Kubernetes configurations
    * [ ] [setup_k8s.sh][setup_k8s]
    * [ ] [locust-master-controller.yml][locust_master_controller]
    * [ ] [locust-master-service.yml][locust_master_service]
    * [ ] [locust-worker-controller.yml][locust_worker_controller]
4. Documentation
    * [ ] [load test docs][load_test_docs]

[artifact_registry]: https://console.cloud.google.com/artifacts/docker/spheric-keel-331521/us-west1/locust-merino?project=spheric-keel-331521
[circle_ci]: https://circleci.com/docs/
[circle_config_yml]: https://github.com/mozilla-services/merino-py/blob/main/.circleci/config.yml
[cloud]: https://console.cloud.google.com/home/dashboard?q=search&referrer=search&project=spheric-keel-331521&cloudshell=false
[conserv]: https://drive.google.com/drive/folders/1rvCpmwGuLt4COH6Zw6vSyu_019_sB3Ux
[docker]: https://docs.docker.com/
[docker_compose]:https://github.com/mozilla-services/merino-py/blob/main/tests/load/docker-compose.yml
[dockerfile]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/Dockerfile
[grafana]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/merino-py-application-and-infrastructure?orgId=1&refresh=1m&var-environment=stagepy
[jenkins_load_test]: https://github.com/mozilla-services/cloudops-infra/blob/master/projects/merino/Jenkinsfile-stage-py
[kubernetes_panel]: https://console.cloud.google.com/kubernetes/list/overview?cloudshell=false&project=spheric-keel-331521
[locust_environment_variables]: https://docs.locust.io/en/stable/configuration.html#environment-variables
[locust_master_controller]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/kubernetes-config/locust-master-controller.yml
[locust_master_service]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/kubernetes-config/locust-master-service.yml
[locust_worker_controller]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/kubernetes-config/locust-worker-controller.yml
[merino_gcp_stage]: https://console.cloud.google.com/kubernetes/list/overview?project=moz-fx-merino-nonprod-ee93
[merino_history_doc]: https://docs.google.com/document/d/1BGNhKuclUH40Bit9KxYWLiv_N_VnE66uxi9pBFbRWbg/edit
[merino_spreadsheet]: https://docs.google.com/spreadsheets/d/1SAO3QYIrbxDRxzmYIab-ebZXA1dF06W1lT4I1h2R3a8/edit?usp=sharing
[merino_test_plan]: https://docs.google.com/document/d/1v7LDXENPZg37KXeNcznEZKNZ8rQlOhNbsHprFyMXHhs/edit?usp=sharing
[uv]: https://docs.astral.sh/uv/
[uv_lock]: https://github.com/mozilla-services/merino-py/blob/main/uv.lock
[pyproject_toml]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/pyproject.toml
[load_test_docs]: ./load-tests.md
[setup_k8s]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/setup_k8s.sh
