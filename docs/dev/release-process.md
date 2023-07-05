# The Release Process

This project currently follows a [Continuous Deployment][continuous_deployment] process.

[continuous_deployment]: https://en.wikipedia.org/wiki/Continuous_deployment

Whenever a commit is pushed to this repository's `main` branch, a CircleCI workflow is triggered
which performs code checks and runs automated tests. The workflow additionally builds a new Docker
image of the service and pushes that Docker image to the Docker Hub registry (this requires all
previous jobs to pass).

Pushing a new Docker image to the Docker Hub registry triggers a webhook that starts the Jenkins
deployment pipeline (the Docker image tag determines the target environment). The deployment
pipeline first deploys to the [`stage` environment][stage_environment] and subsequently to the
[`production` environment][production_environment].

![Activity diagram of CircleCI main-workflow][activity_circleci_main_workflow]

After the deployment is complete, accessing the [`__version__` endpoint][stage_version] will show
the commit hash of the deployed version, which will eventually match to the one of the latest commit
on the `main` branch (a node with an older version might still serve the request before it is shut
down).

[stage_environment]: ../firefox.md#stage
[production_environment]: ../firefox.md#production
[activity_circleci_main_workflow]: ./circleci_main_workflow.jpg
[stage_version]: https://stage.merino.nonprod.cloudops.mozgcp.net/__version__

## Development Guidelines

Please see the [CONTRIBUTING.md][contributing] docs on commit guidelines and pull request best
practices.

[contributing]: https://github.com/mozilla-services/merino-py/blob/main/CONTRIBUTING.md

## Versioning

The commit hash of the deployed code is considered its version identifier. The commit hash can be
retrieved locally via `git rev-parse HEAD`.

## Load Testing

Load testing can be run locally or as a part of the deployment process. Local execution does not
require any labeling in commit messages. For deployment, you have to add a label to the message of
the commit that you wish to deploy in the form of: `[load test: (abort|warn)]`. In most cases this
will be the merge commit created by merging a GitHub pull request.

`abort` will prevent deployment should the load testing fail while `warn` will warn via Slack and
continue deployment. For detailed specifics on load testing and this convention, please see the
[Load Test README][load_test_readme].

Logs from load tests executed in continuous deployment are available in the `/data` volume of the
Locust master kubernetes pod.

[load_test_readme]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/README.md

## Releasing to production

Developers with write access to the Merino repository will initiate a deployment to production when
a Pull-Request on the Merino GitHub repository is merged to the `main` branch. It is recommended to
merge pull requests during hours when the majority of Contile contributors are online.

While any developer with write access can trigger the deployment to production, the _expectation_ is
that the individual(s) who authored and merged the Pull-Request should do so, as they are the ones
most familiar with their changes and who can tell, by looking at the data, if anything looks
anomalous. Developers **must** monitor the [Merino Application & Infrastructure][merino_app_info]
dashboard for any anomaly, for example significant changes in HTTP response codes, increase in
latency, increased container/cpu/memory usage (most things under the 'Infrastructure' heading).

### What to do if tests fail during deployment?

1. Investigate the cause of the test failure
    - For functional tests (unit, integration or contract), logs can be found on
      [CircleCI][circleci]
    - For performance tests (load), insights can be found on [Grafana][merino_app_info] and in the
      Locust logs or. To access the Locust logs:
      1. Open a cloud shell in the [Merino stage environment][merino_gcp_stage]
      2. Authenticate by executing the following command:
      ```shell
      gcloud container clusters get-credentials merino-nonprod-v1 \
        --region us-west1 --project moz-fx-merino-nonprod-ee93
      ```
      3. Access the data in the Kubernetes pod by executing the following command:
      ```shell
        kubectl exec -it -n locust-merino locust-master-0 -- bash -c "cd /data && /bin/bash"
      ```

2. Fix or mitigate the failure
    - If a fix can be identified in a relatively short time, then submit a fix
    - If the failure is caused by a flaky or intermittent functional test and the risk to the
      end-user experience is low, then the test can be "skipped", using the pytest`xfail`
      [decorator][pytest_xfail] during continued investigation. Example:
      ```python
      @pytest.mark.xfail(reason="Test Flake Detected (ref: DISCO-####)")
      ```
3. Re-Deploy
    - A fix or mitigation will most likely require a PR merge to the `main` branch that will
      automatically trigger the deployment process. If this is not possible, a re-deployment can be
      initiated manually by triggering the CI pipeline in [CircleCI][circleci].

[circleci]: https://app.circleci.com/pipelines/github/mozilla-services/merino-py
[merino_app_info]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/wip-merino-py-application-and-infrastructure?orgId=1&from=now-24h&to=now&var-environment=prodpy&refresh=1m
[merino_gcp_stage]: https://console.cloud.google.com/kubernetes/list/overview?project=moz-fx-merino-nonprod-ee93
[pytest_xfail]: https://docs.pytest.org/en/latest/how-to/skipping.html

### What to do if production breaks?

If your latest release causes problems and needs to be rolled back:
don't panic and follow the instructions below:

1. Depending on the severity of the problem, decide if this warrants
   [kicking off an incident][incident_docs];
2. Identify the problematic commit (see instructions below), as it may not necessarily be the latest one!
3. Revert the problematic commit, merge that into GitHub,
   then [deploy the revert commit to production](#releasing-to-production).
    - If a fix can be identified in a relatively short time,
      then you may submit a fix, rather than reverting the problematic commit.

#### Locate problematic commit via "git bisect"
If you are not sure about which commit broke production, you can use `git bisect` to locate the problematic commit as follows:

```sh
# Start the bisect session.
$ git bisect start

# Flag a bad commit, usually you can set it to the latest commit as it's broken
# in production.
$ git bisect bad <commit-hash-for-a-bad-commit>

# Flag a good commit, this can be set to the last known good commit.
# You can use an old commit if you're still unsure, bisect will perform binary
# searches anyway.
$ git bisect good <commit-hash-for-a-good-commit>

# Git will check out a commit in the middle and then you can test it to see if
# the issue is still reproducible. If yes, flag it "bad", otherwise flag it
# "good". Git will use that as input to make the next move until it locates the
# problematic commit.
$ git bisect [bad|good]

# End the bisect session when you're done.
$ git bisect reset
```

[incident_docs]: https://mozilla-hub.atlassian.net/wiki/spaces/MIR/overview
