**Adding Change To Test Warn**

# Merino Load (Locust) Tests

This directory contains source code for the load tests for Merino.

## Related Documentation

* [Merino Load Test Plan][merino_test_plan]
* [Merino Load Test History][merino_history_doc]
* [Merino Load Test Spreadsheet][merino_spreadsheet]

## Opt-In Execution in Staging

To automatically kick off load testing in staging along with your pull request commit, you have to include
a label in your git commit. This must be the merge commit on the `main` branch, since only the most recent commit is checked for the label. This label is in the form of: `[load test: (abort|warn)]`. Take careful note
of correct syntax and spacing within the label. There are two options for load tests, being `abort` and `warn`.

The `abort` label will prevent a `prod` deployment should the load test fail.
Ex. `feat: Add feature ABC [load test: abort]`.

The `warn` label will output a Slack warning should the load test fail, but still allow for `prod` deployment.
Ex. `feat: Add feature XYZ [load test: warn]`.

The commit tag signals load test instructions to Jenkins by modifying the Docker image tag. The Jenkins deployment workflow first deploys to `stage` and then runs load tests if requested. The Docker image tag passed to Jenkins appears as follows:
`^(?P<environment>stage|prod)(?:-(?P<task>\w+)-(?P<onfailure>warn|abort))?-(?P<commit>[a-z0-9]+)$`.

## Local Execution

Follow the steps bellow to execute the load tests locally:

### Setup Environment

#### 1. Configure Environment Variables

The following variables can be set in `tests\load\docker-compose.yml`:

| Environment Variable                             | Node(s)         | Description                                                                               |
|--------------------------------------------------|-----------------|-------------------------------------------------------------------------------------------|
| LOAD_TESTS__LOGGING_LEVEL                        | master & worker | Level for the logger in the load tests as an int (`10` for `DEBUG`, `20` for `INFO` etc.) |
| MERINO_REMOTE_SETTINGS__SERVER                   | master & worker | Server URL of the Kinto instance containing suggestions                                   |
| MERINO_REMOTE_SETTINGS__BUCKET                   | master & worker | Kinto bucket with the suggestions                                                         |
| MERINO_REMOTE_SETTINGS__COLLECTION               | master & worker | Kinto collection with the suggestions                                                     |
| MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH | master & worker | The minimum character limit set for long domain suggestion indexing                       |
| MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT    | master & worker | The minimum character limit set for short domain suggestion indexing                      |
| MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT  | master & worker | File path to the json file of domains                                                     |
| (*OPTIONAL*) LOCUST_CSV                          | master          | Store current request stats to files in CSV format with given prefix (Example: `merino`)  |

#### 2. Host Locust via Docker

Execute the following from the repository root:
```shell
make load-tests
```

### Run Test Session

#### 1. Start Load Test

* In a browser navigate to `http://localhost:8089/`
* Setup parameters:
  * Number of users: 75
  * Spawn rate: 2
  * Host: http://merino:8000 
  * Run time (optional): 10m
* Select "Start Swarming"

#### 2. Stop Load Test

Select the 'Stop' button in the top right hand corner of the Locust UI, after the 
desired test duration has elapsed. If the 'Run time' is set in step 1, the load test 
will stop automatically.

#### 3. Analyse Results

* See [Distributed GCP Execution - Analyse Results](#3-analyse-results-1)
* Only client-side measures, provided by Locust, are available for local execution

### Clean-up Environment

#### 1. Remove Load Test Docker Containers

Execute the following from the repository root:
```shell
make load-tests-clean
```

## Distributed GCP Execution

Follow the steps bellow to execute the distributed load tests on GCP:

### Setup Environment

#### 1. Start a GCP Cloud Shell

The load tests can be executed from the [contextual-services-test-eng cloud shell][cloud].

#### 2. Configure the Bash Script

* The `setup_k8s.sh` file, located in the `tests\load` directory, contains shell 
commands to **create** a GKE cluster, **setup** an existing GKE cluster or **delete** 
a GKE cluster
  * Execute the following from the root directory, to make the file executable:
    ```shell
    chmod +x tests/load/setup_k8s.sh
    ```

#### 3. Create the GCP Cluster

* Execute the `setup_k8s.sh` file and select the **create** option, in order to 
  initiate the process of creating a cluster, setting up the env variables and 
  building the docker image
  ```shell
  ./tests/load/setup_k8s.sh
  ```
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

### Run Test Session

#### 1. Start Load Test

* In a browser navigate to `http://$EXTERNAL_IP:8089`
   
  This url can be generated via command
  ```bash
  EXTERNAL_IP=$(kubectl get svc locust-master -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
  echo http://$EXTERNAL_IP:8089
  ```
* Setup parameters:
  * Number of users: 75
  * Spawn rate: 2
  * Host: 'https://stagepy.merino.nonprod.cloudops.mozgcp.net' 
  * Duration (Optional): 10m
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
  is required to be 200ms or less (`p95 <= 200ms`)
* Locust reports client-side latency via the "merino_stats.csv" file and the UI 
  (under the "Statistics" tab or the "Charts" tab)
  * _Warning!_ A Locust worker with too many users will bottleneck RPS and inflate 
    client-side latency measures
* [Grafana][grafana] reports server-side latency via the "p95 latency" chart 

#### 4. Report Results

* Results should be recorded in the [Merino Load Test Spreadsheet][merino_spreadsheet]
* Optionally, the Locust reports can be saved and linked in the spreadsheet:
  * Download the results via command:
      ```bash
      kubectl cp <master-pod-name>:/home/locust/merino_stats.csv merino_stats.csv
      kubectl cp <master-pod-name>:/home/locust/merino_exceptions.csv merino_exceptions.csv
      kubectl cp <master-pod-name>:/home/locust/merino_failures.csv merino_failures.csv
      ```
    The `master-pod-name` can be found at the top of the pod list:
      ```bash 
      kubectl get pods -o wide
      ```
  * Upload the files to [gist][gist] and record the links

### Clean-up Environment

#### 1. Delete the GCP Cluster

Execute the `setup_k8s.sh` file and select the **delete** option
```shell
./tests/load/setup_k8s.sh
```

[cloud]: https://console.cloud.google.com/home/dashboard?q=search&referrer=search&project=spheric-keel-331521&cloudshell=false
[gist]: https://gist.github.com/new
[grafana]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/merino-py-application-and-infrastructure?orgId=1&refresh=1m&var-environment=stagepy
[merino_test_plan]: https://docs.google.com/document/d/1v7LDXENPZg37KXeNcznEZKNZ8rQlOhNbsHprFyMXHhs/edit?usp=sharing
[merino_history_doc]: https://docs.google.com/document/d/1BGNhKuclUH40Bit9KxYWLiv_N_VnE66uxi9pBFbRWbg/edit
[merino_spreadsheet]: https://docs.google.com/spreadsheets/d/1SAO3QYIrbxDRxzmYIab-ebZXA1dF06W1lT4I1h2R3a8/edit?usp=sharing
