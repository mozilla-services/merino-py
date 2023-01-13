# Merino Load (Locust) Tests

This directory contains source code for the load tests for Merino.

## Related Documentation

* [Merino Load Test Plan][merino_test_plan]
* [Merino Load Test History][merino_history_doc]
* [Merino Load Test Spreadsheet][merino_spreadsheet]


## Local Execution

Follow the steps bellow to execute the load tests locally: 

### Setup Environment

1. Configure Environment Variables

   Variables can be set in `tests\load\docker-compose.yml`.

| Environment Variable      | Node(s)         | Description                                                                               |
|---------------------------|-----------------|-------------------------------------------------------------------------------------------|
| LOAD_TESTS__LOGGING_LEVEL | master & worker | Level for the logger in the load tests as an int (`10` for `DEBUG`, `20` for `INFO` etc.) |
| KINTO__SERVER_URL         | master & worker | Server URL of the Kinto instance containing suggestions                                   |
| KINTO__BUCKET             | master & worker | Kinto bucket with the suggestions                                                         |
| KINTO__COLLECTION         | master & worker | collection with the suggestions                                                           |
| (*OPTIONAL*) LOCUST_CSV   | master          | Store current request stats to files in CSV format with given prefix (Example: `merino`)  |

2. Host Locust via Docker

    Execute the following from the repository root:
    ```shell
    docker-compose \
      -f tests/load/docker-compose.yml up \
      --scale locust_worker=4
    ```

### Run Test Session

1. Start Load Tests

    * In a browser navigate to `http://localhost:8089/`
    * Set the `Number of users` (Example: 300) and `Spawn rate` (Example: 50)
    * Select `Start Swarming`

2. Stop Load Tests

    Select the 'Stop' button in the top right hand corner of the Locust UI, after the 
    desired test duration has elapsed (Example: 65 minutes).

3. Analyse Results

    * Load tests are considered as 'passing' if no failures are detected during 
      execution
    * Exceptions are not expected during test execution and are more commonly related 
      to errors in the load test execution, not Merino

### Clean-up Environment

1. Remove Load Test Docker Containers

    Execute the following from the repository root:
    ```shell
    docker-compose -f tests/load/docker-compose.yml down
    ```

## Distributed GCP Execution

Follow the steps bellow to execute the distributed load tests on GCP: 

### Setup Environment

1. Start a GCP Cloud Shell

    The load tests can be executed from the 
    [contextual-services-test-eng cloud shell][cloud].

2. Configure the Bash Script

    * The `setup_k8s.sh` file, located in the `tests\load` directory, contains shell 
      commands to **create** a GKE cluster, **setup** an existing GKE cluster or 
      **delete** a GKE cluster
    * Execute the following from the `tests\load` directory, to make the file 
      executable:
        ```shell
        chmod +x setup_k8s.sh
        ```

3. Create the GCP Cluster

    * Execute the `setup_k8s.sh` file and select the **create** option, in order to 
      initiate the process of creating a cluster, setting up the env variables and 
      building the docker image
        ```shell
        ./setup_k8s.sh
        ```
    * The cluster creation process will take some time. It is considered complete, once 
      an external IP is assigned to the `locust_master` node. Monitor the assignment via
      a watch loop:
        ```bash
        kubectl get svc locust-master --watch
        ```
   * The number of workers is defaulted to 10, but can be modified with the 
     `kubectl scale` command. Example (20 workers):
        ```bash
        kubectl scale deployment/locust-worker --replicas=20
        ```

### Run Test Session

1. Start Load Tests

    * In a browser navigate to `http://$EXTERNAL_IP:8089`
      
      This url can be generated via command
        ```bash
        EXTERNAL_IP=$(kubectl get svc locust-master -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
        echo http://$EXTERNAL_IP:8089
        ```
    * Set the `Number of users` (Example: 300) and `Spawn rate` (Example: 50)
    * Select `Start Swarming`

2. Stop Load Tests

    Select the 'Stop' button in the top right hand corner of the Locust UI, after the 
    desired test duration has elapsed (Example: 65 minutes).

3. Analyse & Report Results

    * Results should be recorded in the 
      [Merino Load Test Spreadsheet][merino_spreadsheet]
    * Load tests are considered as 'passing' if:
      * No failures are detected during execution
      * No anomalous trends are detected on the 
        [Grafana Merino-py Application & Infrastructure][grafana] dashboard
    * Exceptions are not expected during test execution and are more commonly related 
      to errors in the load test execution, not Merino
    * Optionally, the locust reports can be saved and linked in the 
      [Merino Load Test Spreadsheet][merino_spreadsheet]:
      * Download the results via command: 
      
          **WARNING!** Gathering logs via the Locust UI may cause the service to crash.
          
          ```bash
          kubectl cp <master-pod-name>:/home/locust/merino_stats.csv merino_stats.csv
          kubectl cp <master-pod-name>:/home/locust/merino_exceptions.csv merino_exceptions.csv
          kubectl cp <master-pod-name>:/home/locust/merino_failures.csv merino_failures.csv
          ```
        The `master-pod-name` can be found at the top of the pod list:
          ```bash 
          kubectl get pods -o wide
          ```
      * Aggregate the merino_stats.csv file:
          ```bash
          cat merino_stats.csv | grep -Ev "^GET," > merino_stats.csv.tmp
          mv merino_stats.csv.tmp merino_stats.csv
          ```
      * Upload the files to [gist][gist] and record the links

### Clean-up Environment

1. Delete the GCP Cluster

    Execute the `setup_k8s.sh` file and select the **delete** option
    ```shell
    ./setup_k8s.sh
    ```

[cloud]: https://console.cloud.google.com/home/dashboard?q=search&referrer=search&project=spheric-keel-331521&cloudshell=false
[gist]: https://gist.github.com/new
[grafana]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/merino-py-application-and-infrastructure?orgId=1
[merino_test_plan]: https://docs.google.com/document/d/1v7LDXENPZg37KXeNcznEZKNZ8rQlOhNbsHprFyMXHhs/edit?usp=sharing
[merino_history_doc]: https://docs.google.com/document/d/1BGNhKuclUH40Bit9KxYWLiv_N_VnE66uxi9pBFbRWbg/edit
[merino_spreadsheet]: https://docs.google.com/spreadsheets/d/1SAO3QYIrbxDRxzmYIab-ebZXA1dF06W1lT4I1h2R3a8/edit?usp=sharing
