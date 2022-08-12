# Contribution Guidelines

Anyone is welcome to contribute to this project. Feel free to get in touch with
other community members on [Matrix](https://chat.mozilla.org), the mailing list or through issues here on
GitHub.

## Bug Reports

You can file issues here on GitHub. Please try to include as much information as
you can and under what conditions you saw the issue.

## Sending Pull Requests

Patches should be submitted as pull requests (PR).

Before submitting a PR:
- Ensure you are pulling from the most recent `main` branch and install dependencies with Poetry. See 
  [See the README](/README.md) for more details.
- Your code must run and pass all the automated tests before you submit your PR
  for review. [See the README](/README.md) for information on linting, formatting and testing. "Work in progress" or "Draft" pull requests are allowed to be submitted, but
  should be clearly labeled as such and should not be merged until all tests
  pass and the code has been reviewed.
- Ideally, your patch should include new tests that cover your changes. It is your and
  your reviewer's responsibility to ensure your patch includes adequate tests.

When submitting a PR:
- You agree to license your code under the project's open source license
  ([MPL 2.0](/LICENSE)).
- Base your branch off the current `main`.
- Add both your code and new tests if relevant.
- [Sign](https://docs.github.com/en/github/authenticating-to-github/managing-commit-signature-verification/signing-commits) your git commit.
- Run tests, linting and formatting checks to make sure your code complies with established standards.
(e.g. No warnings are returned for python: "`make lint`", "`make test`", "`make format`")
- Ensure your changes do not reduce code coverage of the test suite.
- Please do not include merge commits in pull requests; include only commits
  with the new relevant code.

WIP: See the main
[documentation](https://github.com/mozilla-services/merino-py)
for information on prerequisites, installing, running and testing.

## Code Review

This project is production Mozilla code and subject to our [engineering practices and quality standards](https://developer.mozilla.org/en-US/docs/Mozilla/Developer_guide/Committing_Rules_and_Responsibilities). Every patch must be peer reviewed.

## Git Commit Guidelines & Branch Naming

We loosely follow the [Angular commit guidelines](https://github.com/angular/angular.js/blob/master/CONTRIBUTING.md#type)
of `<type>: <subject>` where `type` must be one of:

* **feat**: A new feature
* **fix**: A bug fix
* **docs**: Documentation only changes
* **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing
  semi-colons, etc)
* **refactor**: A code change that neither fixes a bug or adds a feature
* **perf**: A code change that improves performance
* **test**: Adding missing tests
* **chore**: Changes to the build process or auxiliary tools and libraries such as documentation
  generation

Name the branch using this nomenclature with the `<type>` followed by a forward slash, followed by a dash-seperated description of the task. Ex. `feat/add-sentry-sdk-MOZ-1234`. Note, if associated with a Jira ticket, synchronization with Jira and GitHub is possible by appending the suffix of the Jira ticket to the branch name (`-MOZ-1234` in the example above). This can be added anywhere in the branch name, but adding to the end is ideal. You can also include the Jira issue at the end of ccommit messages to keep the task up to date. See Jira Docs for referencing issues [here](https://support.atlassian.com/jira-software-cloud/docs/reference-issues-in-your-development-work/)

### Subject

The subject contains succinct description of the change:

* use the imperative, present tense: "change" not "changed" nor "changes"
* don't capitalize first letter
* no dot (.) at the end

### Body

In order to maintain a reference to the context of the commit, add
`Closes #<issue_number>` if it closes a related issue or `Issue #<issue_number>`
if it's a partial fix.

You can also write a detailed description of the commit: Just as in the
**subject**, use the imperative, present tense: "change" not "changed" nor
"changes" It should include the motivation for the change and contrast this with
previous behavior.

### Footer

The footer should contain any information about **Breaking Changes** and is also
the place to reference GitHub issues that this commit **Closes**.

### Example

A properly formatted commit message should look like:

```
feat: give the developers a delicious cookie

Properly formatted commit messages provide understandable history and
documentation. This patch will provide a delicious cookie when all tests have
passed and the commit message is properly formatted.

BREAKING CHANGE: This patch requires developer to lower expectations about
    what "delicious" and "cookie" may mean. Some sadness may result.

Closes #314, #975
```
