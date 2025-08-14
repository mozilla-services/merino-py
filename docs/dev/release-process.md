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
[stage_version]: https://merino.services.allizom.org/__version__

## Release Best Practices

The _expectation_ is that the author of the change will:

- merge pull requests during hours when the majority of contributors are online
- monitor the [Merino Application & Infrastructure][merino_app_info] dashboard for any anomaly

## Versioning

The commit hash of the deployed code is considered its version identifier. The commit hash can be
retrieved locally via `git rev-parse HEAD`.

## Load Testing

Load testing can be performed either locally or during the deployment process. During deployment,
load tests are run against the staging environment before Merino-py is promoted to production.

Load tests in continuous deployment are controlled by adding a specific label to the commit message
being deployed. The format for the label is `[load test: (abort|skip|warn)]`. Typically, this label
is added to the merge commit created when a GitHub pull request is integrated.

- `abort`: Stops the deployment if the load test fails.
- `skip`: Skips load testing entirely during deployment.
- `warn`: Proceeds with the deployment even if the load test fails, but sends a warning notification
  through Slack.

If no label is included in the commit message, the default behavior is to run the load test and
issue a warning if it fails.

For more detailed information about load testing procedures and conventions, please refer to the
[Load Test README][load_test_readme].

Logs from load tests executed in continuous deployment are available in the `/data` volume of the
Locust master kubernetes pod.

[load_test_readme]: https://github.com/mozilla-services/merino-py/blob/main/tests/load/README.md

### What to do if production breaks?

If your latest release causes problems and needs to be rolled back:
don't panic and follow the instructions in the [Rollback Runbook](../operations/rollback.md).

### What to do if tests fail during deployment?

Please refer to [What to do with Test Failures in CI?](../operations/testfailures.md)
