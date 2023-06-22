# The Release Process

This project currently follows a [Continuous Deployment][continuous_deployment] process.

[continuous_deployment]: https://en.wikipedia.org/wiki/Continuous_deployment

Whenever a commit is pushed to this repository's `main` branch, a CircleCI workflow is triggered which performs code checks and runs automated tests. The workflow additionally builds a new Docker image of the service and pushes that Docker image to the Docker Hub registry (this requires all previous jobs to pass).

Pushing a new Docker image to the Docker Hub registry triggers a webhook that starts the Jenkins deployment pipeline (the Docker image tag determines the target environment). The deployment pipeline first deploys to the [`stage` environment](../firefox.md#stage) and subsequently to the [`production` environment](../firefox.md#production).

![Activity diagram of CircleCI main-workflow][activity_circleci_main_workflow]

After the deployment is complete, accessing the [`__version__` endpoint][stage_version] will show the commit hash of the deployed version, which will eventually match to the one of the latest commit on the `main` branch (a node with an older version might still serve the request before it is shut down).

[stage_version]: https://stage.merino.nonprod.cloudops.mozgcp.net/__version__

## Development Guidelines
Please see the [CONTRIBUTING.md][contributing] docs on commit guidelines and pull request best practices.

## Versioning
The commit hash of the deployed code is considered its version identifier. The commit hash can be retrieved locally via `git rev-parse HEAD`.

## Load Testing
Load testing can be run locally or as a part of the deployment process. Local execution does not require any labeling in commit messages. For deployment, you have to add a label to the message of the commit that you wish to deploy in the form of: `[load test: (abort|warn)]`. In most cases this will be the merge commit created by merging a GitHub pull request.

Abort will prevent deployment should the load testing fail while warn will simply warn via Slack and continue deployment. For detailed specifics on load testing and this convention, please see the relevant documentation: [load-testing-docs]: /tests/load/README.md].

## Releasing to production
Developers with write access to the Merino repository will initiate a deployment to production when a Pull-Request on the Merino GitHub repository is merged to the `main` branch.
Developers **must** monitor the [Merino Application & Infrastructure][merino_app_info] dashboard for any anomaly, for example significant changes in HTTP response codes, increase in latency, cpu/memory usage (most things under the infrastructure heading).

While any developer with write access can trigger the deployment to production, the _expectation_ is that individual(s) who authored and merged the Pull-Request should do so, as they are the ones most familiar with their changes and who can tell, by looking at the data, if anything looks anomalous.
In general authors should feel _responsible_ for the changes they make and shepherd these changes through to deployment.

[merino_app_info]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/wip-merino-py-application-and-infrastructure?orgId=1&from=now-24h&to=now&var-environment=prodpy&refresh=1m

## What to do if production breaks?
If your latest release causes problems and needs to be rolled back:
don't panic and follow the instructions below:

1. Depending on the severity of the problem, decide if this warrants [kicking off an incident][incident_docs];
2. Identify the problematic commit (see instructions below), as it may not necessarily be the latest one!
3. Revert the problematic commit, merge that into GitHub,
   then [deploy the revert commit to production](#releasing-to-production).
   - If a fix can be identified in a relatively short time,
     then you may submit a fix, rather than reverting the problematic commit.

### Locate problematic commit via "git bisect"
If you are not sure about which commit broke production, you can use `git bisect` to locate the problematic commit as follows:

```sh
# Start the bisect session.
$ git bisect start

# Flag a bad commit, usually you can set it to the latest commit as it's broken
# in production.
$ git bisect bad <commit-hash-for-a-bad-commit>

# Flag a good commit, this can be set to the last known good commit.
# You can use an old commit If you're still unsure, bisect will perform binary
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
[contributing]: ../../CONTRIBUTING.md
[load-testing-docs]: /tests/load/README.md
[activity_circleci_main_workflow]: ./circleci_main_workflow.jpg
